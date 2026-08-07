"""The database reads behind the tools. No MCP, no formatting."""

from __future__ import annotations

from typing import Literal

from core.db import session
from core.knowledge import Snapshot
from core.models import Chunk, Document
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# The corpus is a fixed snapshot for the life of the process, so resolve the
# repo/commit once. `False` distinguishes "looked, found nothing" from "not
# looked yet" without a second flag.
_snapshot: Snapshot | None | Literal[False] = False


async def snapshot_info() -> Snapshot | None:
    global _snapshot
    if _snapshot is False:
        async with session() as db:
            row = (
                await db.execute(
                    select(Document.repo, Document.commit_sha)
                    .where(Document.source_type == "code")
                    .limit(1)
                )
            ).first()
        _snapshot = Snapshot(repo=row[0], commit=row[1]) if row else None
    return _snapshot


async def document(db: AsyncSession, path: str) -> tuple[str, int] | None:
    """The file's content and total line count, or None if it is not indexed."""
    return (
        await db.execute(
            select(Document.content, Document.line_count).where(Document.path == path)
        )
    ).first()


async def symbols_for(db: AsyncSession, path: str) -> list[tuple[str, str, int, int]]:
    """The named spans of a file as (name, kind, start_line, end_line).

    Code files carry real symbols; prose files have none, so markdown falls
    back to its heading breadcrumbs, which serve the same navigational
    purpose. Ordered by position in the file either way.
    """
    rows = (
        await db.execute(
            select(Chunk.symbol, Chunk.symbol_kind, Chunk.start_line, Chunk.end_line)
            .where(Chunk.path == path, Chunk.symbol.isnot(None))
            .order_by(Chunk.start_line)
        )
    ).all()
    if rows:
        return [(n, k, a, b) for n, k, a, b in rows]

    headings = (
        await db.execute(
            select(Chunk.heading_path, Chunk.start_line, Chunk.end_line)
            .where(Chunk.path == path, Chunk.heading_path.isnot(None))
            .order_by(Chunk.start_line)
        )
    ).all()
    return [(h, "heading", a, b) for h, a, b in headings]
