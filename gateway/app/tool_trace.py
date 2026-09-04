"""Reassembling a turn's tool calls from the frames that announce them.

The interceptor reports a call in pieces so the UI can render a card the
moment work starts; the database wants one complete record per call instead.
`ToolTrace` folds the frames back together, keyed by `call_id`, reading the
events already on their way to the client -- so the persisted trace cannot
disagree with the one the user watched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .protocol import RetrievalHits, ServerEvent, ToolCall, ToolResult


@dataclass
class ToolRow:
    """One tool call, complete enough to write down."""

    call_id: str
    ordinal: int
    name: str
    arguments: dict[str, Any]
    # reaches the database as "running" for a turn cancelled mid-call: the
    # call never reported back, and "error" would invent an outcome
    status: str = "running"
    preview: str | None = None
    hits: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int | None = None


class ToolTrace:
    def __init__(self) -> None:
        # insertion-ordered, which is call order: `ordinal` is written from it
        self._rows: dict[str, ToolRow] = {}

    def observe(self, event: ServerEvent) -> None:
        """Fold one frame in; irrelevant frames are ignored, so the caller can
        hand it every event without a type check of its own."""
        if isinstance(event, ToolCall):
            self._rows[event.call_id] = ToolRow(
                call_id=event.call_id,
                ordinal=len(self._rows),
                name=event.name,
                arguments=event.arguments,
            )
        elif isinstance(event, ToolResult):
            if (row := self._rows.get(event.call_id)) is not None:
                row.status = event.status
                row.preview = event.preview
                row.duration_ms = event.duration_ms
        elif isinstance(event, RetrievalHits):
            if (row := self._rows.get(event.call_id)) is not None:
                row.hits = [hit.model_dump() for hit in event.hits]

    def rows(self) -> list[ToolRow]:
        return list(self._rows.values())
