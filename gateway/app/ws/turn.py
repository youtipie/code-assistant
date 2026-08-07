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

from agent import openai_model, run_turn

from ..config import settings
from ..outbox import Outbox
from ..store import store
from ..tasks import TaskRegistry

log = logging.getLogger(__name__)

# Turn-closing writes that outlive their drive_turn task; lifespan waits for
# them before close_db() tears down the engine they are still writing through.
persists = TaskRegistry("turn persistence")


async def drive_turn(outbox: Outbox, session_id: str, turn_id: str, text: str) -> None:
    chunks: list[str] = []
    finish: TurnEnd | None = None
    setup_error: Exception | None = None

    gen = run_turn(
        session_id,
        turn_id,
        text,
        max_steps=settings.max_steps,
        turn_timeout_seconds=settings.turn_timeout_seconds,
    )
    try:
        # Inside the try (not before it) so a cancel/failure landing on
        # either write still runs the finally below and closes the turn out
        # instead of leaving a client that already got turn.start waiting
        # forever. store.finish_turn no-ops if start_turn's row never landed.
        await store.append_message(session_id, "user", {"text": text})
        await store.start_turn(session_id, turn_id, openai_model)
        async with contextlib.aclosing(gen) as events:
            async for event in events:
                outbox.send(event)
                if isinstance(event, TextDelta):
                    chunks.append(event.text)
                elif isinstance(event, TurnEnd):
                    finish = event
    except Exception as exc:
        # asyncio.CancelledError is a BaseException, not an Exception, so a
        # real cancellation (explicit Cancel, timeout, disconnect) passes
        # through this clause untouched. What lands here is something outside
        # run_turn's own error handling blowing up instead -- a store write,
        # or run_turn's own repair_dangling_tool_calls call before its try.
        # Recorded distinctly so the finally below doesn't misfile a real bug
        # as a user cancel.
        setup_error = exc
        log.exception("turn setup/drive failed")
        raise
    finally:
        # Deferred until after the loop, not awaited inline per event: an
        # await here would give a Cancel/timeout a chance to land outside
        # run_turn's own exception handling, skipping its TurnEnd yield and
        # leaving this turn stuck "running". Why it goes through
        # TaskRegistry rather than a plain await is documented there.
        if finish is None:
            # run_turn never got to yield its own TurnEnd (setup failed, or
            # the generator was torn down via GeneratorExit before doing so)
            # -- the client already got turn.start for this turn_id, so it
            # needs an explicit terminal event too, not just a closed DB row.
            reason, message = _fallback_close(setup_error)
            outbox.send(TurnEnd(turn_id=turn_id, reason=reason, message=message))
        reply = "".join(chunks)
        await persists.spawn(
            _persist_turn(session_id, turn_id, reply, finish, setup_error)
        )


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
    finish: TurnEnd | None,
    setup_error: Exception | None,
) -> None:
    # finish_turn before append_message: closing the turn row is the write
    # that matters most -- if this task is killed partway through, better to
    # lose the trailing assistant message than to leave the row "running".
    if finish is not None:
        await store.finish_turn(
            turn_id,
            finish.reason,
            prompt_tokens=finish.prompt_tokens,
            completion_tokens=finish.completion_tokens,
            error=finish.error,
        )
    else:
        status, error = _fallback_close(setup_error)
        await store.finish_turn(turn_id, status, error=error)
    if reply:
        await store.append_message(
            session_id, "assistant", {"text": reply}, turn_id=turn_id
        )
    await store.touch_session(session_id)
