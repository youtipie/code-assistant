"""Chunking markdown by heading, then by paragraph when a section is too long.

Headings carry the breadcrumb (`heading_path`) that gives a prose chunk its
context, standing in for the symbol name a code chunk has.
"""

from __future__ import annotations

import re

from .base import MAX_CHARS, MIN_CHARS, OVERLAP_CHARS, Chunk

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_FRONT_KEY = re.compile(r"^(title|sidebar_label|description):\s*(.+)$")


def _frontmatter_title(lines: list[str]) -> str | None:
    if lines[:1] != ["---"]:
        return None
    for line in lines[1:20]:
        if line.strip() == "---":
            break
        match = _FRONT_KEY.match(line.strip())
        if match and match.group(1) == "title":
            return match.group(2).strip().strip("\"'")
    return None



def chunk_markdown(text: str, path: str) -> list[Chunk]:
    lines = text.splitlines()
    title = _frontmatter_title(lines)
    prefix = f"{title} - {path}" if title else path
    sections: list[tuple[list[str], int, list[str]]] = []
    stack: list[str] = []
    current: list[str] = []
    start = 1
    in_fence = False
    in_frontmatter = lines[:1] == ["---"]

    for i, line in enumerate(lines, start=1):
        if in_frontmatter:
            if i > 1 and line.strip() == "---":
                in_frontmatter = False
            continue

        if _FENCE.match(line):
            in_fence = not in_fence

        heading = None if in_fence else _HEADING.match(line)
        if heading:
            if current and any(x.strip() for x in current):
                sections.append((current, start, list(stack)))
            level = len(heading.group(1))
            title = heading.group(2).strip()
            stack = stack[: level - 1] + [title]
            current = [line]
            start = i
        else:
            current.append(line)

    if current and any(x.strip() for x in current):
        sections.append((current, start, list(stack)))

    chunks: list[Chunk] = []
    for body, line_no, crumbs in _merge_short(sections):
        breadcrumb = " > ".join(crumbs) if crumbs else None
        body_text = "\n".join(body).strip()
        if len(body_text) < MIN_CHARS:
            continue
        for piece, offset in _split_prose(body_text):
            chunks.append(
                Chunk(
                    text=piece,
                    start_line=line_no + offset,
                    end_line=line_no + offset + piece.count("\n"),
                    heading_path=breadcrumb,
                    context_header=(
                        prefix + (f" > {breadcrumb}" if breadcrumb else "")
                    ),
                )
            )
    return chunks


def _merge_short(
    sections: list[tuple[list[str], int, list[str]]],
) -> list[tuple[list[str], int, list[str]]]:
    merged: list[tuple[list[str], int, list[str]]] = []
    pending: tuple[list[str], int, list[str]] | None = None

    for body, line_no, crumbs in sections:
        if pending is None:
            pending = (body, line_no, crumbs)
            continue
        if len("\n".join(pending[0]).strip()) < MIN_CHARS:
            pending = (pending[0] + body, pending[1], pending[2])
        else:
            merged.append(pending)
            pending = (body, line_no, crumbs)

    if pending is not None:
        if merged and len("\n".join(pending[0]).strip()) < MIN_CHARS:
            last = merged.pop()
            merged.append((last[0] + pending[0], last[1], last[2]))
        else:
            merged.append(pending)
    return merged


def _split_paragraphs(text: str) -> list[str]:
    blocks: list[str] = []
    buf: list[str] = []
    fence: str | None = None

    for line in text.split("\n"):
        match = _FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)
            buf.append(line)
            continue
        if fence is not None:
            buf.append(line)
            if match and match.group(1) == fence:
                fence = None
            continue
        if not line.strip():
            if buf:
                blocks.append("\n".join(buf))
                buf = []
        else:
            buf.append(line)

    if buf:
        blocks.append("\n".join(buf))
    return blocks


def _split_prose(text: str) -> list[tuple[str, int]]:
    if len(text) <= MAX_CHARS:
        return [(text, 0)]

    parts: list[tuple[str, int]] = []
    paragraphs = _split_paragraphs(text)
    buf: list[str] = []
    line_offset = 0
    consumed = 0

    for para in paragraphs:
        candidate = "\n\n".join([*buf, para])
        if buf and len(candidate) > MAX_CHARS:
            joined = "\n\n".join(buf)
            parts.append((joined, line_offset))
            consumed += joined.count("\n") + 2
            tail = buf[-1]
            if len(tail) > OVERLAP_CHARS or "```" in tail or "~~~" in tail:
                buf = [para]
                line_offset = consumed
            else:
                buf = [tail, para]
                line_offset = consumed - tail.count("\n") - 2
        else:
            buf.append(para)

    if buf:
        parts.append(("\n\n".join(buf), line_offset))
    return parts
