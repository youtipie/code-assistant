"""The events `agent.run_turn` yields and `gateway` sends: one definition.

These were three -- dataclasses in `agent`, pydantic models in `gateway`, and
a field-for-field adapter between them -- so every shape change was a
three-file edit with nothing to catch a miss. `core` owns them because it is
the leaf both members already depend on.

Two things here are load-bearing for the wire format:

* **Field declaration order is the serialised key order.** Pydantic emits base
  fields first, then each subclass's own in declaration order. Declare `type`
  first among a subclass's fields; do not hoist a `type` onto `ServerEvent`,
  which would emit it ahead of `seq`.
* **These models must stay mutable.** `gateway.outbox.Outbox.send` stamps
  `seq` and `session_id` by plain attribute assignment, so no `frozen=True`
  and no `validate_assignment=True`.

Imports only pydantic, so `agent` yielding these stays persistence-free.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ServerEvent(BaseModel):
    """Envelope on every server -> client frame.

    Producers build events with the defaults; `Outbox.send` stamps both at
    send time, so `seq` is per-connection and monotonic.
    """

    seq: int = 0
    session_id: str | None = None


class TextDelta(ServerEvent):
    type: Literal["text.delta"] = "text.delta"
    turn_id: str
    text: str


class ToolCall(ServerEvent):
    type: Literal["tool.call"] = "tool.call"
    turn_id: str
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(ServerEvent):
    type: Literal["tool.result"] = "tool.result"
    turn_id: str
    call_id: str
    status: Literal["ok", "error"]
    preview: str | None = None


class RetrievalHit(BaseModel):
    """One passage the UI can link to, built by the knowledge renderer.

    `citation` is the `path:line` form the system prompt tells the model to
    cite, so the UI and the answer text agree on how a source is named.
    """

    path: str
    citation: str
    start_line: int
    source_type: str


class RetrievalHits(ServerEvent):
    """Emitted after context retrieval so the UI can show sources live."""

    type: Literal["retrieval.hits"] = "retrieval.hits"
    turn_id: str
    hits: list[RetrievalHit] = Field(default_factory=list)


class TurnEnd(ServerEvent):
    type: Literal["turn.end"] = "turn.end"
    turn_id: str
    reason: Literal["completed", "cancelled", "error"]
    # client-facing; populated on reason="error"
    message: str | None = None

    # Persistence-facing, deliberately never on the wire: gateway's
    # _persist_turn reads them off the object instead. `error` is distinct
    # from `message` above -- a recursion-limit hit tells the client "step
    # limit reached" and records "recursion limit" in the DB.
    # NB. exclude=True is not overridable: model_dump(include=...) will not
    # bring these back. Read them as attributes.
    prompt_tokens: int | None = Field(default=None, exclude=True)
    completion_tokens: int | None = Field(default=None, exclude=True)
    error: str | None = Field(default=None, exclude=True)


class ErrorEvent(ServerEvent):
    """Dual-origin: `run_turn` yields it mid-turn (`internal_error`), and
    gateway mints it for protocol-level refusals (`bad_request`,
    `no_active_turn`, `busy`) where no turn is in flight."""

    type: Literal["error"] = "error"
    code: str
    message: str
    # Declared last so existing frames keep their key order and merely gain a
    # trailing "turn_id": null. Optional because gateway mints this event with
    # no turn in flight (bad_request on a malformed frame, no_active_turn,
    # busy); it is populated only when a turn actually failed mid-flight.
    turn_id: str | None = None


# What run_turn can yield. The gateway-only events (session.created,
# turn.start, heartbeat, pong) stay in gateway/app/protocol.py -- the agent
# cannot produce them, since gateway owns the socket and mints turn ids.
AgentEvent = TextDelta | ToolCall | ToolResult | RetrievalHits | TurnEnd | ErrorEvent

__all__ = [
    "AgentEvent",
    "ErrorEvent",
    "RetrievalHit",
    "RetrievalHits",
    "ServerEvent",
    "TextDelta",
    "ToolCall",
    "ToolResult",
    "TurnEnd",
]
