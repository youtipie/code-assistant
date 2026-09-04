from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from sqlalchemy import Float, Integer, Row, cast, func, literal, select
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Chunk

log = logging.getLogger(__name__)

RRF_K = 60

ANY_TERM_WEIGHT = 0.5

CANDIDATES = 50


def _ranked_cte(name, order_by, filters, *match):
    """One branch of the fusion: the top CANDIDATES chunks by `order_by`,
    each labelled with its 1-based rank. `match` is the branch's own
    full-text predicate, if it has one -- the dense branch does not."""
    return (
        select(
            Chunk.id.label("id"),
            func.row_number().over(order_by=order_by).label("rank"),
        )
        .where(*match, *filters)
        .order_by(order_by)
        .limit(CANDIDATES)
        .cte(name)
    )


async def fetch_candidates(
    db: AsyncSession,
    query: str,
    embedding: list[float],
    limit: int,
    source_type: str | None = None,
    path_prefix: str | None = None,
) -> Sequence[Row]:
    filters = []
    if source_type:
        filters.append(Chunk.source_type == source_type)
    if path_prefix:
        filters.append(Chunk.path.startswith(path_prefix))

    dense = _ranked_cte("dense", Chunk.embedding.cosine_distance(embedding), filters)

    # websearch_to_tsquery tolerates human input (quotes, OR, -) without
    # raising, which plainto_/to_tsquery do not. The config argument is
    # regconfig, not text: without the cast psycopg binds a varchar and
    # Postgres finds no matching function.
    tsquery = func.websearch_to_tsquery(
        cast(literal("english"), REGCONFIG), query
    )
    lexical = _ranked_cte(
        "lexical",
        func.ts_rank(Chunk.search_tsv, tsquery).desc(),
        filters,
        Chunk.search_tsv.op("@@")(tsquery),
    )

    # a partial-match branch, so a query where no chunk carries every term
    # still ranks the ones carrying some
    words = re.findall(r"[A-Za-z0-9_]{2,}", query)
    terms = list(dict.fromkeys(w.lower() for w in words))
    if not terms:
        # to_tsquery("") raises; fall back to the AND branch alone
        terms = ["\u0000none\u0000"]
    any_query = func.to_tsquery(
        cast(literal("english"), REGCONFIG), " | ".join(terms)
    )
    any_term = _ranked_cte(
        "any_term",
        func.ts_rank(Chunk.search_tsv, any_query).desc(),
        filters,
        Chunk.search_tsv.op("@@")(any_query),
    )

    fused_id = func.coalesce(dense.c.id, lexical.c.id, any_term.c.id).label("id")
    score = (
        func.coalesce(1.0 / (RRF_K + cast(dense.c.rank, Float)), 0.0)
        + func.coalesce(1.0 / (RRF_K + cast(lexical.c.rank, Float)), 0.0)
        + ANY_TERM_WEIGHT
        * func.coalesce(1.0 / (RRF_K + cast(any_term.c.rank, Float)), 0.0)
    ).label("score")

    fused = (
        select(
            fused_id,
            score,
            cast(dense.c.rank, Integer).label("dense_rank"),
            cast(lexical.c.rank, Integer).label("lexical_rank"),
        )
        .select_from(
            dense.join(lexical, dense.c.id == lexical.c.id, full=True).join(
                any_term,
                func.coalesce(dense.c.id, lexical.c.id) == any_term.c.id,
                full=True,
            )
        )
        .cte("fused")
    )

    # column labels match Hit's field names exactly -- search.py builds Hits
    # from row._mapping, so a rename here must be a rename there
    stmt = (
        select(
            Chunk.id.label("chunk_id"),
            fused.c.score,
            fused.c.dense_rank,
            fused.c.lexical_rank,
            Chunk.source_type,
            Chunk.repo,
            Chunk.path,
            Chunk.language,
            Chunk.symbol,
            Chunk.heading_path,
            Chunk.start_line,
            Chunk.end_line,
            Chunk.text,
        )
        .join(fused, Chunk.id == fused.c.id)
        .order_by(fused.c.score.desc())
        .limit(limit)
    )

    return (await db.execute(stmt)).all()
