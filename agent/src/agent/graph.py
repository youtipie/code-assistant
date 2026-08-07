from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from core.settings import core_settings
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import settings as agent_settings
from .mcp_client import manager
from .prompts import compose_system_prompt

log = logging.getLogger(__name__)

@dataclass
class GraphRuntime:
    """The compiled graph and the connection pool backing its checkpointer.

    Both are process-wide and built together by build_graph(), so they are
    one object rather than two globals that must be kept in step.
    """

    graph: CompiledStateGraph | None = None
    pool: AsyncConnectionPool | None = None


_runtime = GraphRuntime()


FINAL_DIRECTIVE = """\
Your tool budget for this question is used up. Answer now from what you have \
already gathered. Do not ask for more searches or file reads.

If what you found answers the question, answer it. If it does not, say so \
directly -- "I could not find this in the indexed corpus" -- then summarise \
what you did find, what it rules out, and what the user could ask instead. An \
honest dead end is a useful answer; silence is not.
"""


class AgentState(MessagesState):
    steps: int


def _model(with_tools: bool = True) -> ChatOpenAI:
    options: dict[str, Any] = {
        "model": agent_settings.openai_model,
        "api_key": agent_settings.openai_api_key,
        "streaming": True,
        "stream_usage": True,
    }
    if agent_settings.openai_use_responses_api:
        options["use_responses_api"] = True
    if agent_settings.openai_reasoning_effort:
        options["reasoning_effort"] = agent_settings.openai_reasoning_effort
    else:
        options["temperature"] = 0

    tools = manager.tools()
    model = ChatOpenAI(**options)
    return model.bind_tools(tools) if with_tools and tools else model


async def _agent_node(state: AgentState, config: RunnableConfig) -> dict:
    steps = state.get("steps", 0)
    # run_turn puts the budget here alongside thread_id; it is genuinely
    # per-turn, so it travels with the turn rather than sitting in a global
    finalising = steps >= config["configurable"]["max_steps"]
    tools = manager.tools()

    messages = [
        SystemMessage(
            content=compose_system_prompt(
                tools, finalising, manager.unavailable, manager.active(), agent_settings
            )
        ),
        *state["messages"],
    ]
    if finalising:
        log.info("tool budget exhausted, forcing a final answer")
        messages.append(SystemMessage(content=FINAL_DIRECTIVE))

    response = await _model(with_tools=not finalising).ainvoke(messages)
    return {"messages": [response], "steps": steps + 1}


def _should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


async def build_graph():
    pool = AsyncConnectionPool(
        conninfo=core_settings.database_url,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            "prepare_threshold": 0,
        },
    )
    await pool.open(wait=True, timeout=30)

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    builder = StateGraph(AgentState)
    builder.add_node("agent", _agent_node)
    builder.add_node("tools", ToolNode(manager.tools()))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", _should_continue, ["tools", END])
    builder.add_edge("tools", "agent")

    _runtime.pool = pool
    _runtime.graph = builder.compile(checkpointer=checkpointer)
    log.info("agent graph ready (%d tools)", len(manager.tools()))
    return _runtime.graph


async def close_graph() -> None:
    _runtime.graph = None
    if _runtime.pool is not None:
        await _runtime.pool.close()
        _runtime.pool = None


def graph():
    if _runtime.graph is None:
        raise RuntimeError("graph not built; call build_graph() first")
    return _runtime.graph


async def repair_dangling_tool_calls(config: dict) -> int:
    state = await graph().aget_state(config)
    messages = state.values.get("messages", []) if state.values else []
    if not messages:
        return 0

    # find the most recent assistant message that requested tools
    last_call_index = None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], AIMessage) and messages[i].tool_calls:
            last_call_index = i
            break
    if last_call_index is None:
        return 0

    requested = {tc["id"] for tc in messages[last_call_index].tool_calls}
    answered = {
        m.tool_call_id
        for m in messages[last_call_index + 1 :]
        if isinstance(m, ToolMessage)
    }
    missing = requested - answered
    if not missing:
        return 0

    log.warning("repairing %d dangling tool call(s)", len(missing))
    await graph().aupdate_state(
        config,
        {
            "messages": [
                ToolMessage(
                    content="Interrupted before this tool returned.",
                    tool_call_id=call_id,
                )
                for call_id in missing
            ]
        },
        # attribute the write to the tools node: without as_node the graph
        # cannot tell where to resume from and rejects the update
        as_node="tools",
    )
    return len(missing)
