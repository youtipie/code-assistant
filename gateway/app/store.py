from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Literal

from core.db import session
from core.events import TurnStats
from core.models import Message, Session, ToolInvocation, Turn
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from .tool_trace import ToolRow

Role = Literal["user", "assistant", "system", "tool"]
TurnStatus = Literal["completed", "cancelled", "error"]


class Store:
    async def create_session(
        self, title: str | None = None, owner: str | None = None
    ) -> str:
        row = Session(title=title, owner=owner)
        async with session() as db:
            db.add(row)
            await db.flush()
            return str(row.id)

    async def ensure_session(self, session_id: str, owner: str | None = None) -> bool:
        async with session() as db:
            result = await db.execute(
                insert(Session)
                .values(id=uuid.UUID(session_id), owner=owner)
                .on_conflict_do_nothing(index_elements=["id"])
                .returning(Session.id)
            )
            return result.scalar_one_or_none() is not None

    async def set_title(self, session_id: str, title: str) -> None:
        async with session() as db:
            row = await db.get(Session, uuid.UUID(session_id))
            if row is not None and not row.title:
                row.title = title[:120]

    async def touch_session(self, session_id: str) -> None:
        async with session() as db:
            row = await db.get(Session, uuid.UUID(session_id))
            if row is not None:
                row.updated_at = func.now()

    async def append_message(
        self,
        session_id: str,
        role: Role,
        content: dict[str, Any],
        turn_id: str | None = None,
    ) -> None:
        async with session() as db:
            db.add(
                Message(
                    session_id=uuid.UUID(session_id),
                    turn_id=uuid.UUID(turn_id) if turn_id else None,
                    role=role,
                    content=content,
                )
            )

    async def start_turn(self, session_id: str, turn_id: str, model: str) -> None:
        row = Turn(
            id=uuid.UUID(turn_id),
            session_id=uuid.UUID(session_id),
            status="running",
            model=model,
        )
        async with session() as db:
            db.add(row)

    async def finish_turn(
        self,
        turn_id: str,
        status: TurnStatus,
        stats: TurnStats | None = None,
        error: str | None = None,
    ) -> None:
        """Close the turn row out.

        `stats` is the object `TurnEnd` carries, so the row and the frame
        cannot drift apart. None leaves the columns NULL: a zero would claim
        the turn was free.
        """
        async with session() as db:
            row = await db.get(Turn, uuid.UUID(turn_id))
            if row is None:
                return
            row.status = status
            row.ended_at = func.now()
            row.error = error
            if stats is None:
                return
            row.model = stats.model
            row.prompt_tokens = stats.prompt_tokens
            row.completion_tokens = stats.completion_tokens
            row.cached_tokens = stats.cached_tokens
            row.cache_write_tokens = stats.cache_write_tokens
            row.cost_usd = (
                None if stats.cost_usd is None else Decimal(str(stats.cost_usd))
            )
            row.ttft_ms = stats.ttft_ms
            row.duration_ms = stats.duration_ms
            row.steps = stats.steps
            row.tool_calls = stats.tool_calls

    async def save_tool_calls(self, turn_id: str, calls: Sequence[ToolRow]) -> None:
        """Write down the tool calls a turn made, so a reloaded conversation
        shows the work and not just the answer.

        One statement per turn rather than a write per call: the trace is only
        read back whole, and writing as events arrive would put a round trip
        inside the loop feeding the socket.
        """
        if not calls:
            return
        async with session() as db:
            db.add_all(
                [
                    ToolInvocation(
                        turn_id=uuid.UUID(turn_id),
                        call_id=call.call_id,
                        ordinal=call.ordinal,
                        name=call.name,
                        arguments=call.arguments,
                        status=call.status,
                        preview=call.preview,
                        hits=call.hits,
                        duration_ms=call.duration_ms,
                    )
                    for call in calls
                ]
            )


store = Store()
