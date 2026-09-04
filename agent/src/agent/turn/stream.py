"""The stream/wakeup race, as one primitive.

`run_turn` needs two things to reach it promptly: the graph's next LLM message,
and the tool events the interceptor buffers while a tool node runs. Only the
first is a stream. Racing them here lets `run_turn` be a plain `async for` over
a single sequence of "a message arrived" / "some events arrived".

Why a race at all: `stream_mode="messages"` produces nothing while a tool node
runs, so a tool call buffered by the interceptor would otherwise sit unseen
until the *next* token chunk -- which, for a tool node, is only after the tool
has already returned.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

from ..turn_state import BufferedEvent, TurnState

log = logging.getLogger(__name__)

_STREAM_END = object()


@dataclass
class Message:
    """The graph produced a message."""

    payload: object


@dataclass
class Buffered:
    """The interceptor buffered events for the client."""

    events: list[BufferedEvent]


Step = Message | Buffered


async def steps(stream: AsyncIterator, state: TurnState) -> AsyncIterator[Step]:
    """Yield each graph message and each batch of buffered events, whichever
    is ready first, until the stream ends.

    The caller must drain once more after this generator finishes: cancelling
    the stream can let an in-flight tool call complete and buffer, and a
    generator cannot reliably yield from its own cleanup.
    """
    # No `await` sits between these two lines and the try/finally, so nothing
    # can cancel this task in the gap and leave either task
    # uncreated-but-referenced.
    stream_next = asyncio.ensure_future(_anext(stream))
    wake = asyncio.ensure_future(state.updated.wait())
    try:
        while True:
            done, _pending = await asyncio.wait(
                (stream_next, wake), return_when=asyncio.FIRST_COMPLETED
            )

            if wake in done:
                if events := drain(state):
                    yield Buffered(events)
                wake = asyncio.ensure_future(state.updated.wait())

            if stream_next in done:
                outcome = stream_next.result()
                # A tool.result/retrieval.hits pair can land in the gap
                # between the interceptor's last wakeup and the graph
                # resuming past the tool node -- drain again so nothing waits
                # for the *next* wakeup to appear.
                if events := drain(state):
                    yield Buffered(events)
                if outcome is _STREAM_END:
                    break
                stream_next = asyncio.ensure_future(_anext(stream))
                yield Message(outcome)
    finally:
        # asyncio.wait never cancels the tasks it was waiting on, so on any
        # exit -- break, exception, cancellation -- a surviving stream_next
        # would keep driving astream() with nothing left consuming it.
        await _cancel_and_drain(stream_next)
        await _cancel_and_drain(wake)


def drain(state: TurnState) -> list[BufferedEvent]:
    events, state.buffer[:] = list(state.buffer), []
    state.updated.clear()
    return events


async def _anext(stream: AsyncIterator) -> object:
    """`await stream.__anext__()`, with `StopAsyncIteration` turned into a
    sentinel return value.

    This coroutine is wrapped in a Task and raced via asyncio.wait, and a Task
    that raises StopAsyncIteration looks like one that raised anything else:
    `async for`'s special-casing reaches the coroutine it calls directly, not
    a Task around it. Every other exception is left to propagate through
    `stream_next.result()`, where run_turn's except clauses handle it.
    """
    try:
        return await stream.__anext__()
    except StopAsyncIteration:
        return _STREAM_END


async def _cancel_and_drain(task: asyncio.Task) -> None:
    """Cancel `task` if still running, then retrieve its outcome either way,
    so it never lingers un-awaited.

    This only ever runs from a finally block, with no except clause of its own
    around it, so a swallowed cancellation would let run_turn fall through to
    TurnEnd(reason="completed") for a turn that was actually cancelled. The
    CancelledError from our own `task.cancel()` is expected; a *fresh*
    cancellation of run_turn's task landing during this await must keep
    propagating, and `cancelling()` tells them apart -- it only increments on
    a new .cancel() against the current task.

    The early return is for the caller arriving while `task`'s own exception
    is propagating: re-awaiting would re-raise and re-log it as a cleanup
    failure.
    """
    if task.done() and not task.cancelled():
        exc = task.exception()
        if exc is not None and exc is sys.exc_info()[1]:
            return

    if not task.done():
        task.cancel()

    current = asyncio.current_task()
    pending_cancels = current.cancelling() if current is not None else 0
    try:
        await task
    except asyncio.CancelledError:
        if current is not None and current.cancelling() > pending_cancels:
            raise
    except Exception:
        log.exception("stream cleanup failed")
