from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Annotated, Any

from core.db import session
from core.events import RetrievalHit, TurnStats
from core.models import Document, Message, Session, ToolInvocation, Turn
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent import status as agent_status

from .access_rules import session_visible

router = APIRouter(prefix="/api", tags=["api"])


class SessionSummary(BaseModel):
    id: str
    title: str | None
    created_at: str
    updated_at: str
    turn_count: int


class ToolCallOut(BaseModel):
    """One persisted tool call, shaped for the card that renders it.

    `RetrievalHit` is the model the `retrieval.hits` frame carries, so a
    replayed card and a live one are fed identical source links.
    """

    call_id: str
    name: str
    arguments: dict[str, Any]
    # "ok" | "error" | "running", the last meaning the turn died mid-flight
    status: str
    preview: str | None
    hits: list[RetrievalHit]
    duration_ms: int | None


class MessageOut(BaseModel):
    id: int
    role: str
    text: str
    turn_id: str | None
    created_at: str
    # Nullable but required, no default -- the rule schema_export.py applies
    # to the socket events: optional-and-nullable is two shapes for the client.
    stats: TurnStats | None
    # empty for user messages, and for assistant turns recorded before the
    # trace was persisted -- which is not the same as having made no calls
    tools: list[ToolCallOut]


class ServerStatus(BaseModel):
    name: str
    description: str
    available: bool
    tool_count: int


class Snapshot(BaseModel):
    repo: str
    commit: str


class Status(BaseModel):
    model: str
    corpus_repos: list[str]
    snapshots: list[Snapshot]
    servers: list[ServerStatus]
    tools: list[str]


ClientId = Annotated[str | None, Header(alias="X-Client-Id")]


async def owned_session(
    session_id: uuid.UUID, client_id: ClientId = None
) -> AsyncIterator[tuple[AsyncSession, Session]]:
    """Resolve a path session_id to a row the caller is allowed to see, and
    hand back the open DB session so the endpoint can keep working through it.

    Malformed ids never reach here -- FastAPI validates the annotation and
    422s first. A session that exists but belongs to someone else 404s rather
    than 403s: telling a stranger that an id is real is itself a disclosure.
    """
    async with session() as db:
        row = await db.get(Session, session_id)
        if not session_visible(
            row is not None,
            row.owner if row is not None else None,
            client_id,
        ):
            raise HTTPException(status_code=404, detail="no such session")
        yield db, row


OwnedSession = Annotated[tuple[AsyncSession, Session], Depends(owned_session)]


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    client_id: ClientId = None, limit: int = 50
) -> list[SessionSummary]:
    turn_counts = (
        select(Turn.session_id, func.count().label("n"))
        .group_by(Turn.session_id)
        .subquery()
    )
    async with session() as db:
        rows = (
            await db.execute(
                select(Session, func.coalesce(turn_counts.c.n, 0))
                .outerjoin(turn_counts, Session.id == turn_counts.c.session_id)
                .where(Session.owner == client_id)
                .order_by(Session.updated_at.desc())
                .limit(limit)
            )
        ).all()

    return [
        SessionSummary(
            id=str(s.id),
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
            turn_count=n,
        )
        for s, n in rows
    ]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def session_messages(owned: OwnedSession) -> list[MessageOut]:
    db, row = owned
    rows = (
        await db.execute(
            # outer join: user messages carry no turn_id, and an assistant
            # message whose turn row was lost should still be readable
            select(Message, Turn)
            .outerjoin(Turn, Message.turn_id == Turn.id)
            .where(Message.session_id == row.id)
            .order_by(Message.created_at, Message.id)
        )
    ).all()

    # one query for the session, rather than N round trips to open it
    tools = await _tools_of(db, row.id)

    return [
        MessageOut(
            id=m.id,
            role=m.role,
            text=_text_of(m.content),
            turn_id=str(m.turn_id) if m.turn_id else None,
            created_at=m.created_at.isoformat(),
            stats=_stats_of(turn),
            tools=tools.get(m.turn_id, []),
        )
        for m, turn in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(owned: OwnedSession) -> None:
    db, row = owned
    await db.delete(row)


@router.get("/status", response_model=Status)
async def status() -> Status:
    ag = agent_status()
    servers = [
        ServerStatus(
            name=name,
            description=description,
            available=True,
            tool_count=ag.tools_per_server.get(name, 0),
        )
        for name, description in ag.active_servers
    ] + [
        ServerStatus(name=name, description="", available=False, tool_count=0)
        for name in ag.unavailable_servers
    ]

    async with session() as db:
        rows = (
            await db.execute(
                select(Document.repo, Document.commit_sha).distinct()
            )
        ).all()

    return Status(
        model=ag.openai_model,
        corpus_repos=[repo for repo, _ in ag.corpus_repos],
        snapshots=[Snapshot(repo=repo, commit=commit) for repo, commit in rows],
        servers=servers,
        tools=sorted(ag.tools),
    )


async def _tools_of(
    db: AsyncSession, session_id: uuid.UUID
) -> dict[uuid.UUID, list[ToolCallOut]]:
    """Every tool call in the session, grouped by the turn that made it."""
    rows = (
        await db.execute(
            select(ToolInvocation)
            .join(Turn, ToolInvocation.turn_id == Turn.id)
            .where(Turn.session_id == session_id)
            # ordinal, not created_at: calls issued in the same millisecond
            # would otherwise renumber the cards between reloads
            .order_by(ToolInvocation.turn_id, ToolInvocation.ordinal)
        )
    ).scalars()

    grouped: dict[uuid.UUID, list[ToolCallOut]] = defaultdict(list)
    for row in rows:
        grouped[row.turn_id].append(
            ToolCallOut(
                call_id=row.call_id,
                name=row.name,
                arguments=row.arguments,
                status=row.status,
                preview=row.preview,
                hits=[RetrievalHit(**hit) for hit in row.hits],
                duration_ms=row.duration_ms,
            )
        )
    return grouped


def _stats_of(turn: Turn | None) -> TurnStats | None:
    """Rebuild a turn's stats from its row, or None if it has none.

    `duration_ms` is the marker: written if and only if the whole TurnStats
    was, so it tells "no stats recorded" from a genuine zero.
    """
    if turn is None or turn.duration_ms is None:
        return None
    return TurnStats(
        model=turn.model or "",
        prompt_tokens=turn.prompt_tokens or 0,
        completion_tokens=turn.completion_tokens or 0,
        cached_tokens=turn.cached_tokens or 0,
        cache_write_tokens=turn.cache_write_tokens or 0,
        cost_usd=None if turn.cost_usd is None else float(turn.cost_usd),
        ttft_ms=turn.ttft_ms,
        duration_ms=turn.duration_ms,
        steps=turn.steps or 0,
        tool_calls=turn.tool_calls or 0,
    )


def _text_of(content: Any) -> str:
    if isinstance(content, dict):
        return str(content.get("text", ""))
    return str(content)
