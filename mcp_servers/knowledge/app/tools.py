"""The four knowledge tools.

Plain async functions returning the models in `core.knowledge`; `server.py`
registers them with FastMCP, which serialises the return value. Keeping the
registration out of here means this module is callable directly.
"""

from __future__ import annotations

from core.db import session
from core.embedding import embed_query
from core.knowledge import (
    FileWindow,
    Outline,
    SearchHit,
    SearchResult,
    Symbol,
    ToolError,
)
from core.retrieval.search import search

from .queries import document, snapshot_info, symbols_for
from .symbol_resolution import SymbolCandidate, resolve_symbol, symbol_window

MAX_READ_CHARS = 8000
MIN_WINDOW = 120


async def _search(query: str, limit: int, source_type: str) -> SearchResult:
    vector = embed_query(query)
    async with session() as db:
        hits = await search(db, query, vector, limit=limit, source_type=source_type)
    return SearchResult(
        query=query,
        snapshot=await snapshot_info(),
        hits=[
            SearchHit(
                path=h.path,
                start_line=h.start_line,
                end_line=h.end_line,
                symbol=h.symbol,
                heading_path=h.heading_path,
                source_type=h.source_type,
                text=h.text[:2000],
            )
            for h in hits
        ],
    )


async def search_docs(query: str, limit: int = 6) -> SearchResult:
    return await _search(query, limit, "doc")


async def search_code(query: str, limit: int = 6) -> SearchResult:
    return await _search(query, limit, "code")


async def outline(path: str) -> Outline:
    async with session() as db:
        spans = await symbols_for(db, path)

    return Outline(
        path=path,
        symbols=[
            Symbol(name=n, kind=k, start_line=a, end_line=b) for n, k, a, b in spans
        ],
    )


def _render_window(lines: list[str], start_line: int, end_line: int) -> tuple[str, int]:
    """Number the lines in [start_line, end_line], stopping at the character
    budget. Returns the text and the last line actually served, which is
    start_line - 1 when nothing fit."""
    rendered: list[str] = []
    served_end = start_line - 1
    used = 0
    for n, line in enumerate(lines[start_line - 1 : end_line], start=start_line):
        row_text = f"{n:>5}  {line}"
        if used + len(row_text) > MAX_READ_CHARS:
            break
        rendered.append(row_text)
        used += len(row_text) + 1
        served_end = n
    return "\n".join(rendered), served_end


async def read_file(
    path: str,
    symbol: str | None = None,
    start_line: int = 1,
    end_line: int = 200,
) -> FileWindow | ToolError:
    # --- look the document up ---
    async with session() as db:
        row = await document(db, path)
        if row is None:
            return ToolError(error="not_found", path=path)

        content, total = row

        # --- resolve a symbol to a line range, if one was asked for ---
        resolved = None
        if symbol:
            candidates = [
                SymbolCandidate(name, a, b)
                for name, _kind, a, b in await symbols_for(db, path)
            ]
            match = resolve_symbol(symbol, candidates)
            if match is None:
                return ToolError(error="symbol_not_found", path=path, symbol=symbol)
            resolved = match.name
            start_line, end_line = symbol_window(match)

    # --- clamp the window ---
    # an explicit range too small to be useful is widened; a symbol's own
    # range is exactly what was asked for and is left alone
    if not resolved and end_line - start_line < MIN_WINDOW:
        end_line = start_line + MIN_WINDOW

    lines = content.splitlines()
    start_line = max(1, start_line)
    end_line = min(end_line, len(lines))

    # --- render ---
    text, served_end = _render_window(lines, start_line, end_line)
    truncated = served_end < end_line
    return FileWindow(
        path=path,
        symbol=resolved,
        start_line=start_line,
        end_line=served_end,
        total_lines=total,
        truncated=truncated,
        next_start_line=served_end + 1 if truncated else None,
        text=text,
    )


TOOLS = (search_docs, search_code, outline, read_file)
