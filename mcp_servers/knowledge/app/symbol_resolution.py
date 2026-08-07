from __future__ import annotations

from dataclasses import dataclass

SYMBOL_MARGIN = 5


@dataclass
class SymbolCandidate:
    name: str
    start_line: int
    end_line: int


def resolve_symbol(
    symbol: str, candidates: list[SymbolCandidate]
) -> SymbolCandidate | None:
    """Exact match beats dotted-suffix match (`Class.method` for `method`)
    beats substring match. Ties within a tier go to the earliest candidate."""
    needle = symbol.strip().lower()

    for matches in (
        lambda name: name == needle,
        lambda name: name.endswith(f".{needle}"),
        lambda name: needle in name,
    ):
        found = next((c for c in candidates if matches(c.name.lower())), None)
        if found is not None:
            return found

    return None


def symbol_window(resolved: SymbolCandidate) -> tuple[int, int]:
    start = max(1, resolved.start_line - SYMBOL_MARGIN)
    return start, resolved.end_line + SYMBOL_MARGIN
