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
# The agent's events are defined in core.events and re-exported through
# __all__, so this stays gateway's single import site for the wire contract.
# Only the four events gateway itself mints are declared here.


class SessionCreated(ServerEvent):
    type: Literal["session.created"] = "session.created"


class TurnStart(ServerEvent):
    type: Literal["turn.start"] = "turn.start"
    turn_id: str


class Heartbeat(ServerEvent):
    type: Literal["heartbeat"] = "heartbeat"


class Pong(ServerEvent):
    type: Literal["pong"] = "pong"


# Every frame gateway can send, in one name for `schema_export`. Deliberately
# not Annotated[..., Field(discriminator="type")]: pydantic renders that as
# JSON Schema `oneOf`, which json-schema-to-zod turns into an untyped
# `z.any().superRefine(...)`, where `anyOf` becomes a real z.union.
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
