"""Driving one turn and persisting it.

The ordering here is the whole point: a turn that ends -- however it ends --
must reach the client as a terminal event and must not be left `running` in
the database.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Literal

from core.events import TextDelta, TurnEnd
from opentelemetry.trace import Span, Status, StatusCode

from agent import openai_model, run_turn

from ..config import settings
from ..outbox import Outbox
from ..store import store
from ..tasks import TaskRegistry
from ..tool_trace import ToolRow, ToolTrace
from ..tracing import tracer

log = logging.getLogger(__name__)

# Turn-closing writes that outlive their drive_turn task; lifespan waits for
# them before close_db() tears down the engine they are still writing through.
persists = TaskRegistry("turn persistence")


async def drive_turn(outbox: Outbox, session_id: str, turn_id: str, text: str) -> None:
    chunks: list[str] = []
    trace = ToolTrace()
    finish: TurnEnd | None = None
    setup_error: Exception | None = None

    gen = run_turn(
        session_id,
        turn_id,
        text,
        max_steps=settings.max_steps,
        turn_timeout_seconds=settings.turn_timeout_seconds,
    )
    # Opened here rather than inside run_turn: an async generator shares the
    # caller's context, so a span entered inside it would attach and detach
    # across yield boundaries in *this* task's context. Around the `async
    # for`, the generator is always resumed inside the span.
    try:
        with tracer.start_as_current_span(_span_name(text, turn_id)) as span:
            # without this the trace UI files the root under "unknown"
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("session.id", session_id)
            span.set_attribute("turn.id", turn_id)
            span.set_attribute("llm.model_name", openai_model)
            # the trace list renders these columns
            span.set_attribute("input.value", text)
            # Inside the try so a failure on either write still runs the
            # finally below and closes the turn out, rather than leaving a
            # client that already got turn.start waiting forever.
            await store.append_message(session_id, "user", {"text": text})
            await store.start_turn(session_id, turn_id, openai_model)
            async with contextlib.aclosing(gen) as events:
                async for event in events:
                    outbox.send(event)
                    trace.observe(event)
                    if isinstance(event, TextDelta):
                        chunks.append(event.text)
                    elif isinstance(event, TurnEnd):
                        finish = event
                        span.set_attribute("output.value", "".join(chunks))
                        _record(span, event)
    except Exception as exc:
        # CancelledError is a BaseException, so a real cancellation passes
        # through untouched; what lands here is something outside run_turn's
        # own error handling -- a store write, or its repair call. Recorded
        # distinctly so the finally below cannot misfile it as a user cancel.
        setup_error = exc
        log.exception("turn setup/drive failed")
        raise
    finally:
        # Deferred until after the loop: an await inside it would give a
        # Cancel/timeout a chance to land outside run_turn's own exception
        # handling, skipping its TurnEnd and leaving the turn "running".
        if finish is None:
            # run_turn never yielded its own TurnEnd, and the client already
            # got turn.start: it needs a terminal event, not just a closed row
            reason, message = _fallback_close(setup_error)
            outbox.send(TurnEnd(turn_id=turn_id, reason=reason, message=message))
        reply = "".join(chunks)
        await persists.spawn(
            _persist_turn(
                session_id, turn_id, reply, trace.rows(), finish, setup_error
            )
        )


_NAME_LIMIT = 72


def _span_name(text: str, turn_id: str) -> str:
    """Name the turn's span after the question that started it, so the trace
    list has rows that differ by more than a timestamp.

    High cardinality by name is an anti-pattern for a metrics backend that
    aggregates by span name; Phoenix is a trace store and does not.
    """
    question = " ".join(text.split())
    if not question:
        # a turn with no question is a bug worth being able to point at
        return f"turn {turn_id[:8]}"
    if len(question) <= _NAME_LIMIT:
        return question
    return question[: _NAME_LIMIT - 1].rstrip() + "\u2026"


def _record(span: Span, finish: TurnEnd) -> None:
    """Copy the turn's own accounting onto its span.

    Attribute names follow OpenInference's conventions where one exists, so
    the trace UI renders them in its token columns. Cost is the exception:
    Phoenix ignores `llm.cost.total` and prices the LLM spans itself, so that
    attribute is a cross-check, not the number the UI shows.
    """
    span.set_attribute("turn.reason", finish.reason)
    # explicit on both branches: an unset status reads as "never recorded"
    if finish.reason == "completed":
        span.set_status(Status(StatusCode.OK))
    else:
        span.set_status(Status(StatusCode.ERROR, finish.message or finish.reason))
    stats = finish.stats
    if stats is None:
        return
    span.set_attribute("llm.token_count.prompt", stats.prompt_tokens)
    span.set_attribute("llm.token_count.completion", stats.completion_tokens)
    span.set_attribute(
        "llm.token_count.prompt_details.cache_read", stats.cached_tokens
    )
    span.set_attribute(
        "llm.token_count.prompt_details.cache_write", stats.cache_write_tokens
    )
    span.set_attribute("turn.duration_ms", stats.duration_ms)
    span.set_attribute("turn.steps", stats.steps)
    span.set_attribute("turn.tool_calls", stats.tool_calls)
    if stats.ttft_ms is not None:
        span.set_attribute("turn.ttft_ms", stats.ttft_ms)
    if stats.cost_usd is not None:
        span.set_attribute("llm.cost.total", stats.cost_usd)


def _fallback_close(
    setup_error: Exception | None,
) -> tuple[Literal["cancelled", "error"], str | None]:
    # Shared by drive_turn's wire TurnEnd and _persist_turn's DB finish_turn
    # for the "run_turn never yielded its own TurnEnd" case, so the two can't
    # drift apart on what a given turn's outcome actually was.
    if setup_error is not None:
        return "error", str(setup_error)
    return "cancelled", None


async def _persist_turn(
    session_id: str,
    turn_id: str,
    reply: str,
    tools: list[ToolRow],
    finish: TurnEnd | None,
    setup_error: Exception | None,
) -> None:
    # Ordered by what hurts most to lose if this task is killed partway
    # through: closing the turn row out, then the assistant message, then the
    # tool trace -- which also cannot be written before the turn row exists.
    if finish is not None:
        await store.finish_turn(
            turn_id, finish.reason, stats=finish.stats, error=finish.error
        )
    else:
        status, error = _fallback_close(setup_error)
        await store.finish_turn(turn_id, status, error=error)
    if reply:
        await store.append_message(
            session_id, "assistant", {"text": reply}, turn_id=turn_id
        )
    await store.save_tool_calls(turn_id, tools)
    await store.touch_session(session_id)
