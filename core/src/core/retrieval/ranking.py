from __future__ import annotations

from pathlib import PurePosixPath

from .hits import Hit

PER_DIRECTORY_CAP = 3


def diversify(hits: list[Hit], limit: int) -> list[Hit]:
    kept: list[Hit] = []
    seen: dict[str, int] = {}
    overflow: list[Hit] = []

    for hit in hits:
        directory = str(PurePosixPath(hit.path).parent)
        if seen.get(directory, 0) < PER_DIRECTORY_CAP:
            seen[directory] = seen.get(directory, 0) + 1
            kept.append(hit)
        else:
            overflow.append(hit)
        if len(kept) == limit:
            return kept

    return (kept + overflow)[:limit]
