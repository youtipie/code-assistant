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
    # Set by interceptor.py at every state.buffer.append(...) site (no
    # await between the append and the set(), so this always happens
    # before the tool call that produced the event can possibly resolve --
    # see agent.py's run_turn for the consumer). Cleared only by agent.py's
    # _drain(), the sole reader of `buffer`, in the same synchronous
    # statement that snapshots and empties the list -- so a set() can never
    # be cleared out from under events that are still sitting in the
    # buffer, regardless of where run_turn itself happens to suspend.
    updated: asyncio.Event = field(default_factory=asyncio.Event)


_turn_state: ContextVar[TurnState | None] = ContextVar("turn_state", default=None)


def set_turn_state(state: TurnState | None) -> None:
    _turn_state.set(state)


def current_turn_state() -> TurnState | None:
    return _turn_state.get()
