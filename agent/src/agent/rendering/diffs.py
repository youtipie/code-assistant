"""Truncating oversized diffs, and harvesting the paths they mention.

A GitHub diff can be far larger than the model's useful context, so it is cut
at a file boundary rather than mid-hunk and the omission is named explicitly
-- a silently truncated diff reads as a complete one.
"""

from __future__ import annotations

import re

MAX_DIFF_CHARS = 24000

DIFF_PATH = re.compile(r"^diff --git a/(\S+) b/", re.MULTILINE)


def _truncate_diff(raw: str) -> tuple[str, str | None]:
    if len(raw) <= MAX_DIFF_CHARS:
        return raw, None

    files = re.split(r"(?=^diff --git )", raw, flags=re.MULTILINE)
    kept: list[str] = []
    used = 0
    for chunk in files:
        if used + len(chunk) > MAX_DIFF_CHARS and kept:
            break
        kept.append(chunk)
        used += len(chunk)

    kept_paths = DIFF_PATH.findall("".join(kept))
    all_paths = DIFF_PATH.findall(raw)
    missing = [p for p in all_paths if p not in set(kept_paths)]

    note = (
        f"Showing {len(kept_paths)} of {len(all_paths)} changed files in this "
        "diff -- it was too large to return whole, and this method does not "
        "paginate. Not shown: "
        + ", ".join(missing[:12])
        + ("…" if len(missing) > 12 else "")
        + ". Do not describe this as a complete review: say which files you "
        "did not see, or read them with get_file_contents."
    )
    return "".join(kept), note


def _looks_like_diff(raw: str) -> bool:
    return raw.lstrip().startswith("diff --git") or "\n diff --git " in raw[:2000]

