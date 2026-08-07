"""Writing documents and chunks to the database, and reading them back.

`load_documents` and `chunk_all` are both content-hash driven: unchanged
documents are skipped rather than re-embedded, which is what makes a re-run
cheap.
"""

from __future__ import annotations

import logging

from core.db import session
from core.embedding import embed_passages, embed_query
from core.models import Chunk, Document
from core.retrieval.search import search
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from .chunking import chunk_document, embed_text
from .collect import FileRecord

log = logging.getLogger("ingest")

BATCH = 100
EMBED_BATCH = 64


async def load_documents(records: list[FileRecord]) -> tuple[int, int]:
    written = 0
    async with session() as db:
        for start in range(0, len(records), BATCH):
            rows = [
                {
                    "source_type": r.source_type,
                    "repo": r.repo,
                    "commit_sha": r.commit_sha,
                    "path": r.path,
                    "language": r.language,
                    "content": r.content,
                    "content_hash": r.content_hash,
                    "size_bytes": r.size_bytes,
                    "line_count": r.line_count,
                }
                for r in records[start : start + BATCH]
            ]
            stmt = insert(Document).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_documents_repo_path",
                set_={
                    "commit_sha": stmt.excluded.commit_sha,
                    "content": stmt.excluded.content,
                    "content_hash": stmt.excluded.content_hash,
                    "size_bytes": stmt.excluded.size_bytes,
                    "line_count": stmt.excluded.line_count,
                    "indexed_at": func.now(),
                },
                where=Document.content_hash.is_distinct_from(
                    stmt.excluded.content_hash
                ),
            )
            result = await db.execute(stmt.returning(Document.id))
            written += len(result.scalars().all())
    return written, len(records) - written


async def prune(repo: str, keep: list[str]) -> int:
    async with session() as db:
        result = await db.execute(
            delete(Document).where(
                Document.repo == repo, Document.path.not_in(keep)
            )
        )
        return result.rowcount


async def chunk_all(force: bool = False) -> tuple[int, int, int]:
    written = skipped = docs_done = 0

    async with session() as db:
        docs = (
            await db.execute(
                select(
                    Document.id,
                    Document.path,
                    Document.language,
                    Document.source_type,
                    Document.repo,
                    Document.content,
                    Document.content_hash,
                )
            )
        ).all()

    log.info("chunking %d documents", len(docs))

    for doc_id, path, language, source_type, repo, content, doc_hash in docs:
        async with session() as db:
            if not force:
                existing = (
                    await db.execute(
                        select(Chunk.doc_hash)
                        .where(Chunk.document_id == doc_id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if existing == doc_hash:
                    skipped += 1
                    continue
            await db.execute(delete(Chunk).where(Chunk.document_id == doc_id))

        pieces = chunk_document(content, path, language)
        if not pieces:
            continue

        vectors = embed_passages([embed_text(p) for p in pieces], EMBED_BATCH)

        async with session() as db:
            db.add_all(
                [
                    Chunk(
                        document_id=doc_id,
                        ordinal=p.ordinal,
                        source_type=source_type,
                        repo=repo,
                        path=path,
                        language=language,
                        symbol=p.symbol,
                        symbol_kind=p.symbol_kind,
                        heading_path=p.heading_path,
                        start_line=p.start_line,
                        end_line=p.end_line,
                        text=p.text,
                        context_header=p.context_header,
                        search_text=p.search_text,
                        embedding=vec,
                        doc_hash=doc_hash,
                    )
                    for p, vec in zip(pieces, vectors, strict=True)
                ]
            )
        written += len(pieces)
        docs_done += 1
        if docs_done % 50 == 0:
            log.info("  %d documents, %d chunks", docs_done, written)

    return written, skipped, docs_done


async def run_search(query: str, limit: int, source_type: str | None) -> None:
    vector = embed_query(query)
    async with session() as db:
        hits = await search(db, query, vector, limit=limit, source_type=source_type)

    if not hits:
        print("no hits")
        return

    print(f"\n{len(hits)} hits for {query!r}\n")
    for i, hit in enumerate(hits, 1):
        ranks = f"dense={hit.dense_rank or '-'} lex={hit.lexical_rank or '-'}"
        print(f"{i:>2}. [rrf={hit.score:.4f}] {hit.citation}  ({ranks})")
        preview = " ".join(hit.text.split())[:160]
        print(f"    {preview}\n")

