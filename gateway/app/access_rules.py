from __future__ import annotations


def session_visible(exists: bool, owner: str | None, requester: str | None) -> bool:
    """A session belonging to someone else, or that doesn't exist, is reported
    as missing rather than forbidden: its existence is not this caller's business."""
    return exists and owner == requester
