"""Splitting identifiers so a natural-language query can match code.

`generate_invoice` and `InvoiceGenerator` both become "generate invoice" in
the embedded text, so a search for "invoice generation" reaches them.
"""

from __future__ import annotations

import re

_SNAKE = re.compile(r"[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+")
_CAMEL = re.compile(r"[A-Za-z][a-z0-9]*(?:[A-Z][a-z0-9]*)+")
_CAMEL_SPLIT = re.compile(r"(?<!^)(?=[A-Z])")


def split_identifiers(text: str) -> str:
    words: set[str] = set()
    for match in _SNAKE.findall(text):
        words.update(p for p in match.split("_") if len(p) > 1)
    for match in _CAMEL.findall(text):
        words.update(p for p in _CAMEL_SPLIT.split(match) if len(p) > 1)
    return " ".join(sorted(words))


def humanize_path(path: str) -> str:
    stem = re.sub(r"\.[a-z]+$", "", path)
    return " ".join(w for w in re.split(r"[/_\-.]", stem) if len(w) > 1)
