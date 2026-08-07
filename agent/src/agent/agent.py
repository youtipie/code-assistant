from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Literal

from core.events import AgentEvent, ErrorEvent, TextDelta, TurnEnd
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.errors import GraphRecursionError

from .citations import Registry, Rewriter, set_registry
from .graph import graph, repair_dangling_tool_calls
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
    }

    # a previous turn may have been cancelled or aborted mid-tool-call, which
    # leaves the checkpoint in a state OpenAI rejects outright
    await repair_dangling_tool_calls(config)

    prompt_tokens = completion_tokens = 0

    def finish(
        reason: Literal["completed", "cancelled", "error"],
        message: str | None = None,
        error: str | None = None,
    ) -> TurnEnd:
        # closes over the running token counters so every exit path reports
        # what the turn actually spent, however it ended
        return TurnEnd(
            turn_id=turn_id,
            reason=reason,
            message=message,
            prompt_tokens=prompt_tokens or None,
            completion_tokens=completion_tokens or None,
            error=error,
        )

    try:
        async with asyncio.timeout(turn_timeout_seconds):
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
                if piece := _text_of(message):
                    if rendered := rewriter.feed(piece):
                        yield TextDelta(turn_id=turn_id, text=rendered)

            # cancelling the stream can let an in-flight tool call complete
            # and buffer after `steps` has stopped yielding
            for event in drain(state):
                yield event
            if tail := rewriter.flush():
                yield TextDelta(turn_id=turn_id, text=tail)

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
        yield TextDelta(turn_id=turn_id, text=RECURSION_NOTE)
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


def _text_of(message: AIMessageChunk) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )
