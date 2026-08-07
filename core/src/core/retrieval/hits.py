from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Hit:
    chunk_id: int
    score: float
    source_type: str
    repo: str
    path: str
    language: str
    symbol: str | None
    heading_path: str | None
    start_line: int
    end_line: int
    text: str
    dense_rank: int | None
    lexical_rank: int | None

    @property
    def citation(self) -> str:
        return f"{self.path}:{self.start_line}"
