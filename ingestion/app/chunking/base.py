"""What the two chunkers share: the Chunk record and the size bounds.

The markdown and python chunkers are otherwise independent algorithms -- see
`markdown` and `python`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_CHARS = 1600
OVERLAP_CHARS = 200
MIN_CHARS = 60  # below this a chunk is noise (a stub, a lone import line)


@dataclass
class Chunk:
    text: str
    start_line: int
    end_line: int
    ordinal: int = 0
    symbol: str | None = None
    symbol_kind: str | None = None
    heading_path: str | None = None
    context_header: str = ""
    search_text: str = field(default="")
