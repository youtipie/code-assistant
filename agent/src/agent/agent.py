from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Literal

from core.events import AgentEvent, ErrorEvent, TextDelta, TurnEnd, TurnStats
from core.pricing import cost_usd
from core.settings import core_settings
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.errors import GraphRecursionError

from . import scope
from .citations import Registry, Rewriter, set_registry
from .config import settings
from .graph import checkpoint_messages, graph, repair_dangling_tool_calls
from .prompts.text import OFF_TOPIC_REFUSAL
from .turn.stream import Buffered, drain, steps
from .turn_state import TurnState, set_turn_state

log = logging.getLogger(__name__)

RECURSION_NOTE = (
    "\n\n[I ran out of steps on this one. What I found is above; "
    "try asking something narrower.]"
)


async def run_turn(
    session_id: str,
    turn_id: str,
    text: str,
    *,
    max_steps: int,
    turn_timeout_seconds: int,
) -> AsyncIterator[AgentEvent]:
    state = TurnState(turn_id=turn_id)
    set_turn_state(state)
    citations = Registry()
    set_registry(citations)
    rewriter = Rewriter(citations)

    config = {
        "configurable": {"thread_id": session_id, "max_steps": max_steps},
        # max_steps agent+tools pairs, then the forced final answer, plus
        # headroom. The step counter is the real budget; this is a backstop
        # that must sit ABOVE it or it fires first and we lose the answer.
        "recursion_limit": (max_steps + 2) * 2,
        # gateway's instrumentation maps these onto OTel span attributes; a
        # plain dict keeps OpenTelemetry out of agent
        "metadata": {"session_id": session_id, "turn_id": turn_id},
        "run_name": "agent turn",
    }

    history = await checkpoint_messages(config)
    # a previous turn may have been cancelled or aborted mid-tool-call, which
    # leaves the checkpoint in a state OpenAI rejects outright
    await repair_dangling_tool_calls(config, history)

    prompt_tokens = completion_tokens = steps_taken = 0
    cached_tokens = cache_write_tokens = 0
    guard = scope.Verdict(allowed=True)
    started = time.perf_counter()
    ttft: float | None = None

    def answer(piece: str) -> TextDelta:
        nonlocal ttft
        if ttft is None:
            ttft = time.perf_counter()
        return TextDelta(turn_id=turn_id, text=piece)

    def finish(
        reason: Literal["completed", "cancelled", "error"],
        message: str | None = None,
        error: str | None = None,
    ) -> TurnEnd:
        # every exit path reports what the turn spent, cancellations included.
        # The gate's tokens are part of that but were spent on another model:
        # `model` names the one that answered, and _total_cost prices each side.
        stats = TurnStats(
            model=settings.openai_model,
            prompt_tokens=prompt_tokens + guard.prompt_tokens,
            completion_tokens=completion_tokens + guard.completion_tokens,
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
            cost_usd=_total_cost(
                cost_usd(
                    settings.openai_model,
                    prompt_tokens,
                    completion_tokens,
                    cached_tokens,
                    cache_write_tokens,
                    core_settings.prices,
                ),
                guard,
            ),
            ttft_ms=None if ttft is None else round((ttft - started) * 1000),
            duration_ms=round((time.perf_counter() - started) * 1000),
            steps=steps_taken,
            tool_calls=state.calls,
        )
        return TurnEnd(
            turn_id=turn_id,
            reason=reason,
            message=message,
            stats=stats,
            error=error,
        )

    try:
        async with asyncio.timeout(turn_timeout_seconds):
            guard = await scope.check(text, history, settings)
            if not guard.allowed:
                # nothing reaches the checkpoint: a refused question leaves no
                # trace for the next one to be read against
                yield answer(OFF_TOPIC_REFUSAL.format(corpus=settings.corpus_name))
                yield finish("completed")
                return

            stream = graph().astream(
                {"messages": [HumanMessage(content=text)], "steps": 0},
                config=config,
                stream_mode="messages",
            )
            async for step in steps(stream, state):
                if isinstance(step, Buffered):
                    for event in step.events:
                        yield event
                    continue

                message, _meta = step.payload
                if not isinstance(message, AIMessageChunk):
                    continue
                if usage := getattr(message, "usage_metadata", None):
                    prompt_tokens += usage.get("input_tokens", 0)
                    completion_tokens += usage.get("output_tokens", 0)
                    details = usage.get("input_token_details", {})
                    cached_tokens += details.get("cache_read", 0)
                    # LangChain's name for cache writes, priced apart from both
                    cache_write_tokens += details.get("cache_creation", 0)
                    # usage arrives exactly once per LLM call, so this is an
                    # exact hop count; the graph's own `steps` would cost a read
                    steps_taken += 1
                if piece := _text_of(message):
                    if rendered := rewriter.feed(piece):
                        yield answer(rendered)

            # cancelling the stream can let an in-flight tool call complete
            # and buffer after `steps` has stopped yielding
            for event in drain(state):
                yield event
            if tail := rewriter.flush():
                yield answer(tail)

    except asyncio.CancelledError:
        for event in drain(state):
            yield event
        yield finish("cancelled")
        # keeps propagating: the caller's cleanup and asyncio's own
        # cancellation bookkeeping both depend on seeing it
        raise

    except GraphRecursionError:
        for event in drain(state):
            yield event
        log.warning("recursion limit hit on turn %s", turn_id)
        yield answer(RECURSION_NOTE)
        # the client hears "step limit reached"; the DB records the cause
        yield finish("error", "step limit reached", "recursion limit")
        return

    except TimeoutError:
        for event in drain(state):
            yield event
        yield finish("error", "turn timed out", "turn timed out")
        return

    except Exception as exc:
        for event in drain(state):
            yield event
        log.exception("turn failed")
        yield ErrorEvent(code="internal_error", message=str(exc), turn_id=turn_id)
        yield finish("error", str(exc), str(exc))
        return

    finally:
        set_turn_state(None)
        set_registry(None)

    yield finish("completed")


def _total_cost(agent_cost: float | None, guard: scope.Verdict) -> float | None:
    """Spend across both models; None if either side is unpriced, so the UI
    never shows a total quietly missing a component."""
    if agent_cost is None or not guard.ran:
        return agent_cost
    if guard.cost_usd is None:
        return None
    return agent_cost + guard.cost_usd


def _text_of(message: AIMessageChunk) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )
