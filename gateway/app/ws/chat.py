"""The /chat websocket receive loop.

One socket, many turns, and at most one turn in flight at a time -- two
concurrent turns would race on the same conversation history.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from ..config import settings
from ..outbox import Outbox
from ..protocol import (
    Cancel,
    ErrorEvent,
    Heartbeat,
    Ping,
    Pong,
    SessionCreated,
    TurnStart,
    UserMessage,
    ValidationError,
    parse_client_event,
)
from ..store import store
from .turn import drive_turn

log = logging.getLogger(__name__)


async def heartbeat(outbox: Outbox) -> None:
    while True:
        await asyncio.sleep(settings.heartbeat_seconds)
        outbox.send(Heartbeat())


async def chat(ws: WebSocket, client: str | None = None) -> None:
    await ws.accept()
    owner = client[:64] if client else None
    outbox = Outbox(ws)
    writer = asyncio.create_task(outbox.run(), name="outbox")
    beat = asyncio.create_task(heartbeat(outbox), name="heartbeat")

    session_id: str | None = None
    turn: asyncio.Task | None = None

    try:
        while True:
            raw = await ws.receive_json()

            try:
                event = parse_client_event(raw)
            except ValidationError as exc:
                outbox.send(
                    ErrorEvent(code="bad_request", message=exc.errors()[0]["msg"])
                )
                continue

            if isinstance(event, Ping):
                outbox.send(Pong())

            elif isinstance(event, Cancel):
                if turn is not None and not turn.done():
                    turn.cancel()
                else:
                    outbox.send(
                        ErrorEvent(code="no_active_turn", message="nothing to cancel")
                    )

            elif isinstance(event, UserMessage):
                if turn is not None and not turn.done():
                    outbox.send(
                        ErrorEvent(
                            code="busy",
                            message="a turn is already running; cancel it first",
                        )
                    )
                    continue

                # One socket can carry many conversations, so the message
                # decides which one, never the connection: a remembered session
                # would append a client's second conversation to its first.
                if event.session_id:
                    session_id = event.session_id
                    await store.ensure_session(session_id, owner=owner)
                else:
                    session_id = await store.create_session(owner=owner)
                    outbox.session_id = session_id
                    outbox.send(SessionCreated())

                # the first question names the conversation in the sidebar
                await store.set_title(session_id, event.text)

                outbox.session_id = session_id
                # gateway mints turn_id itself; store.start_turn uses this id
                # for the Turn row rather than generating its own, so
                # turn.start/turn.end and the row always agree.
                turn_id = str(uuid.uuid4())
                outbox.send(TurnStart(turn_id=turn_id))
                turn = asyncio.create_task(
                    drive_turn(outbox, session_id, turn_id, event.text), name="turn"
                )

    except WebSocketDisconnect:
        log.info("client disconnected (session=%s)", session_id)
    except Exception:
        log.exception("connection loop failed")
    finally:
        if turn and not turn.done():
            turn.cancel()
            await asyncio.gather(turn, return_exceptions=True)
        beat.cancel()
        await outbox.drain()
        writer.cancel()
        await asyncio.gather(beat, writer, return_exceptions=True)
