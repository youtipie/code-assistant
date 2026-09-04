from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field

from core.events import RetrievalHits, ToolCall, ToolResult

BufferedEvent = ToolCall | ToolResult | RetrievalHits


@dataclass
class TurnState:
    turn_id: str
    seen: set[str] = field(default_factory=set)
    buffer: list[BufferedEvent] = field(default_factory=list)
    # counted where ToolCall events are minted: they leave the buffer through
    # six drain sites, and a tally over those would eventually miss one
    calls: int = 0
    # Set by interceptor.py at every buffer.append() site, with no await in
    # between, and cleared only by drain() in the same synchronous statement
    # that empties the list -- so a set() can never be lost under events still
    # sitting in the buffer, wherever the consumer happens to suspend.
    updated: asyncio.Event = field(default_factory=asyncio.Event)


_turn_state: ContextVar[TurnState | None] = ContextVar("turn_state", default=None)


def set_turn_state(state: TurnState | None) -> None:
    _turn_state.set(state)


def current_turn_state() -> TurnState | None:
    return _turn_state.get()
