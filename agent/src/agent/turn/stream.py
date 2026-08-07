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
        # Runs on every exit: normal break, an exception propagating to
        # run_turn's except clauses, or this task being cancelled (real
        # Cancel, or asyncio.timeout firing) while suspended in the
        # asyncio.wait above. asyncio.wait never cancels the tasks it was
        # waiting on -- that's on the caller -- so without this, stream_next
        # left running would keep driving astream() (and whatever MCP call it
        # is mid-flight on) with nothing left consuming it.
        await _cancel_and_drain(stream_next)
        await _cancel_and_drain(wake)


def drain(state: TurnState) -> list[BufferedEvent]:
    events, state.buffer[:] = list(state.buffer), []
    state.updated.clear()
    return events


async def _anext(stream: AsyncIterator) -> object:
    """`await stream.__anext__()`, with `StopAsyncIteration` turned into a
    sentinel return value.

    Needed because this coroutine is wrapped in a Task and raced via
    asyncio.wait rather than driven by a normal `async for` -- a Task that
    raises StopAsyncIteration is indistinguishable, from the outside, from
    one that raised any other exception; `async for`'s special-casing of
    StopAsyncIteration only applies to the coroutine it calls directly, not
    to a Task wrapping that coroutine. Any other exception (including ones
    raised deep inside a tool call) is left to propagate through
    `stream_next.result()` unchanged -- run_turn's except clauses handle those.
    """
    try:
        return await stream.__anext__()
    except StopAsyncIteration:
        return _STREAM_END


async def _cancel_and_drain(task: asyncio.Task) -> None:
    """Cancel `task` if still running, then retrieve its outcome either way.

    Always awaits so the task's result/exception is retrieved exactly once
    and it never lingers un-awaited (task destroyed while pending, or an
    exception never retrieved). A CancelledError raised by cancelling `task`
    ourselves (or by re-awaiting a task whose cancellation was already
    consumed by the caller via stream_next.result()) is expected and
    swallowed. But if a *fresh* cancellation of run_turn's own task lands
    while this await is in flight -- a second Cancel, or asyncio.timeout
    firing exactly during this cleanup window -- that must keep propagating,
    or it is silently lost: this coroutine only ever runs from a finally
    block, with no enclosing except clause of its own, so a swallowed
    cancellation here would let run_turn fall through to
    TurnEnd(reason="completed") instead of the cancelled/timed-out turn it
    actually was. Task.cancelling() distinguishes the two cases: it only
    increments on a genuine new .cancel() call against the *current* task,
    not on the .cancel() this function issues against `task` (a different
    Task object) or on re-observing an already-delivered one. Any other
    exception (e.g. a failure during the graph stream's own cancellation
    cleanup) is logged, not discarded -- this cleanup path shouldn't mask a
    real bug in the thing being cleaned up.

    If `task` is already done and ended with the exception currently
    propagating through this call (i.e. the caller reached us via a
    finally/except after already pulling that exception out of `task` via
    `.result()`), re-awaiting it here would just re-raise and re-log the
    same failure under a misleading "stream cleanup failed" banner. Detect
    that case via `sys.exc_info()` and return without touching the task
    further -- it has nothing left to cancel or retrieve.
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
