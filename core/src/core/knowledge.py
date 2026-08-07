"""The knowledge MCP server's response contract.

`mcp_servers/knowledge` returns these and FastMCP serialises them;
`agent/rendering.py` parses them back. It lives in `core` -- the leaf both
already depend on -- because the two are separate deployables that must not
import each other, yet need one definition of the shape between them.

Previously each tool hand-built a `json.dumps({...})` and the renderer read
it back with unguarded subscripts against no schema, so a change on one side
failed on the other at runtime, mid-turn.

Imports only pydantic, so parsing a tool result never drags `core.models`
into the persistence-free agent.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Snapshot(BaseModel):
    repo: str
    commit: str


class SearchHit(BaseModel):
    path: str
    start_line: int
    end_line: int
    symbol: str | None = None
    heading_path: str | None = None
    source_type: str
    text: str


class SearchResult(BaseModel):
    query: str
    snapshot: Snapshot | None = None
    hits: list[SearchHit] = []


class Symbol(BaseModel):
    name: str
    kind: str
    start_line: int
    end_line: int


class Outline(BaseModel):
    path: str
    symbols: list[Symbol] = []


class FileWindow(BaseModel):
    path: str
    symbol: str | None = None
    start_line: int
    end_line: int
    total_lines: int
    truncated: bool
    next_start_line: int | None = None
    text: str


class ToolError(BaseModel):
    """A tool outcome the model is expected to read and recover from -- an
    unknown path or symbol -- not a transport failure."""

    error: Literal["not_found", "symbol_not_found"]
    path: str
    symbol: str | None = None
