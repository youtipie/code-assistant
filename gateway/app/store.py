from __future__ import annotations

import uuid
from typing import Any, Literal

from core.db import session
from core.models import Message, Session, Turn
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

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
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        async with session() as db:
            row = await db.get(Turn, uuid.UUID(turn_id))
            if row is None:
                return
            row.status = status
            row.ended_at = func.now()
            row.prompt_tokens = prompt_tokens
            row.completion_tokens = completion_tokens
            row.error = error


store = Store()
