"""The scan report."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .collect import FileRecord


def summarise(records: list[FileRecord]) -> None:
    by_dir: dict[str, list[FileRecord]] = defaultdict(list)
    for r in records:
        parts = Path(r.path).parts
        by_dir["/".join(parts[:2]) if len(parts) > 1 else parts[0]].append(r)

    table = Table()
    table.add_column("directory")
    for heading in ("files", "lines", "KB", "symbols"):
        table.add_column(heading, justify="right")

    def row(name: str, group: list[FileRecord], **kwargs) -> None:
        table.add_row(
            name,
            f"{len(group)}",
            f"{sum(r.line_count for r in group)}",
            f"{sum(r.size_bytes for r in group) // 1024}",
            f"{sum(r.symbol_count for r in group)}",
            **kwargs,
        )

    for key in sorted(by_dir):
        row(key, by_dir[key])
    row("TOTAL", records, style="bold")
    Console().print(table)

    by_lang: dict[str, int] = defaultdict(int)
    for r in records:
        by_lang[r.language] += 1
    print("\nby language: " + ", ".join(f"{k}={v}" for k, v in sorted(by_lang.items())))