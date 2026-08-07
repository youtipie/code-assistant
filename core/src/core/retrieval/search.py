from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .hits import Hit
from .queries import fetch_candidates
from .ranking import diversify as diversify_hits


async def search(
    db: AsyncSession,
    query: str,
    embedding: list[float],
    limit: int = 8,
    source_type: str | None = None,
    path_prefix: str | None = None,
    diversify: bool = True,
) -> list[Hit]:
    # over-fetch so the diversity cap has candidates to choose between
    overfetch = limit * 4 if diversify else limit
    rows = await fetch_candidates(
        db, query, embedding, overfetch, source_type, path_prefix
    )
    hits = [_hit(r) for r in rows]
    return diversify_hits(hits, limit) if diversify else hits[:limit]


def _hit(row) -> Hit:
    """Build a Hit from labelled columns rather than positional indices, so
    reordering queries.py's select can no longer silently mis-bind fields --
    a rename there fails loudly here instead."""
    fields = dict(row._mapping)
    fields["score"] = float(fields["score"])
    return Hit(**fields)
