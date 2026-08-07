"""Splitting a document into the units that get embedded and searched.

Two independent algorithms behind one dispatcher: code is chunked by symbol
(`python`), prose by heading (`markdown`). They share only the `Chunk` record
and the size bounds in `base`.
"""

from __future__ import annotations

from .base import MAX_CHARS, MIN_CHARS, OVERLAP_CHARS, Chunk
from .identifiers import humanize_path, split_identifiers
from .markdown import chunk_markdown
from .python import chunk_python

__all__ = [
    "MAX_CHARS",
    "MIN_CHARS",
    "OVERLAP_CHARS",
    "Chunk",
    "chunk_document",
    "chunk_markdown",
    "chunk_python",
    "embed_text",
    "humanize_path",
    "split_identifiers",
]


def chunk_document(text: str, path: str, language: str) -> list[Chunk]:
    if language == "python":
        chunks = chunk_python(text, path)
    elif language == "markdown":
        chunks = chunk_markdown(text, path)
    else:
        return []

    path_words = humanize_path(path)
    for i, chunk in enumerate(chunks):
        chunk.ordinal = i
        identifiers = split_identifiers(chunk.text) if language == "python" else ""
        chunk.search_text = "\n".join(
            filter(None, [chunk.context_header, path_words, chunk.text, identifiers])
        )
    return chunks


def embed_text(chunk: Chunk) -> str:
    return f"{chunk.context_header}\n\n{chunk.text}"