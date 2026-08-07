from __future__ import annotations

from typing import Annotated, Any, Literal

from core.events import (
    ErrorEvent,
    RetrievalHits,
    ServerEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnEnd,
)
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

# --------------------------------------------------------------------------
# client -> server
# --------------------------------------------------------------------------


class UserMessage(BaseModel):
    type: Literal["user_message"] = "user_message"
    text: str
    session_id: str | None = None


class Cancel(BaseModel):
    type: Literal["cancel"] = "cancel"


class Ping(BaseModel):
    type: Literal["ping"] = "ping"


ClientEvent = Annotated[
    UserMessage | Cancel | Ping,
    Field(discriminator="type"),
]

_client_adapter: TypeAdapter[ClientEvent] = TypeAdapter(ClientEvent)


def parse_client_event(raw: Any) -> ClientEvent:
    return _client_adapter.validate_python(raw)


# --------------------------------------------------------------------------
# server -> client
# --------------------------------------------------------------------------
#
# The events the agent produces are defined once in core.events and imported
# above; they are re-exported through __all__ so this module stays the single
# import site for gateway's own code. Only the four events gateway alone can
# mint -- it owns the socket and the turn ids -- are declared here.


class SessionCreated(ServerEvent):
    type: Literal["session.created"] = "session.created"


class TurnStart(ServerEvent):
    type: Literal["turn.start"] = "turn.start"
    turn_id: str


class Heartbeat(ServerEvent):
    type: Literal["heartbeat"] = "heartbeat"


class Pong(ServerEvent):
    type: Literal["pong"] = "pong"


# Every frame gateway can send, in one name so `schema_export` can hand the
# whole contract to the web client. Deliberately a plain union and not
# Annotated[..., Field(discriminator="type")]: pydantic renders a
# discriminated union as JSON Schema `oneOf`, which json-schema-to-zod turns
# into an untyped `z.any().superRefine(...)`; `anyOf` becomes a real z.union
# that still narrows on `type`.
ServerEventUnion = (
    SessionCreated
    | TurnStart
    | TextDelta
    | TurnEnd
    | RetrievalHits
    | ToolCall
    | ToolResult
    | ErrorEvent
    | Heartbeat
    | Pong
)


__all__ = [
    "ClientEvent",
    "UserMessage",
    "Cancel",
    "Ping",
    "parse_client_event",
    "ValidationError",
    "ServerEvent",
    "ServerEventUnion",
    "SessionCreated",
    "TurnStart",
    "TextDelta",
    "TurnEnd",
    "ErrorEvent",
    "Heartbeat",
    "Pong",
    "RetrievalHits",
    "ToolCall",
    "ToolResult",
]
