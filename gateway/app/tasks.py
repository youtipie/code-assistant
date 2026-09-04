from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


class TaskRegistry:
    """Fire-and-forget work that must still finish before the process exits.

    A turn's closing writes outlive the task that started them -- the socket
    handler cancels that task the moment the client disconnects, which on the
    happy path is right after turn.end. Shielding the write is not enough: a
    cancelled shield orphans the coroutine, so nothing retrieves its exception
    and shutdown does not wait for it. `spawn` keeps the task reachable, and
    `drain` holds shutdown until it is done with the DB engine.
    """

    def __init__(self, name: str, drain_timeout: float = 5.0) -> None:
        self._name = name
        self._drain_timeout = drain_timeout
        self._tasks: set[asyncio.Task] = set()

    async def spawn(self, coro) -> None:
        """Start `coro`, track it, and wait for it -- shielded, so a
        cancellation arriving at this await does not abandon the work."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._forget)
        await asyncio.shield(task)

    def _forget(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        if (exc := task.exception()) is not None:
            log.error("%s failed", self._name, exc_info=exc)

    async def drain(self) -> None:
        if not self._tasks:
            return
        _, pending = await asyncio.wait(self._tasks, timeout=self._drain_timeout)
        if pending:
            log.warning(
                "%d %s task(s) still running at shutdown", len(pending), self._name
            )
