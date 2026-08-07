from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from .protocol import ServerEvent

log = logging.getLogger(__name__)

DRAIN_TIMEOUT_SECONDS = 2.0


class Outbox:
    def __init__(self, ws: WebSocket, maxsize: int = 1000) -> None:
        self._ws = ws
        self._queue: asyncio.Queue[ServerEvent] = asyncio.Queue(maxsize=maxsize)
        self._seq = 0
        self.session_id: str | None = None

    def send(self, event: ServerEvent) -> None:
        self._seq += 1
        event.seq = self._seq
        if event.session_id is None:
            event.session_id = self.session_id
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # A client too slow to drain a 1000-event backlog is gone.
            log.warning("outbox full, dropping event %s", event.type)

    async def run(self) -> None:
        try:
            while True:
                event = await self._queue.get()
                try:
                    await self._ws.send_text(event.model_dump_json())
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # socket closed under us
            log.info("outbox writer stopped: %s", exc)

    async def drain(self) -> None:
        try:
            async with asyncio.timeout(DRAIN_TIMEOUT_SECONDS):
                await self._queue.join()
        except (TimeoutError, asyncio.CancelledError):
            pass
