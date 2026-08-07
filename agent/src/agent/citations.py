from __future__ import annotations

import re
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import dataclass, field

CITATION_RE = re.compile(r"\[(\d{1,2})\]")
RAW_REF_RE = re.compile(r"\b([\w./-]+\.(?:py|mdx?|graphql|ya?ml))(:\d+)?")


@dataclass
class Registry:
    citations: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    external_paths: set[str] = field(default_factory=set)

    def add_reference(self, path: str, line: int) -> int:
        citation = f"{path}:{line}"
        if citation in self.citations:
            return self.citations.index(citation) + 1
        self.citations.append(citation)
        self.paths.append(path)
        return len(self.citations)

    def note_paths(self, paths: Iterable[str]) -> None:
        self.external_paths.update(p for p in paths if p)

    def resolve(self, index: int) -> str | None:
        if 1 <= index <= len(self.citations):
            return self.citations[index - 1]
        return None


_registry: ContextVar[Registry | None] = ContextVar("citations", default=None)


def set_registry(registry: Registry | None) -> None:
    _registry.set(registry)


def registry() -> Registry | None:
    return _registry.get()


class Rewriter:
    def __init__(self, reg: Registry) -> None:
        self._registry = reg
        self._buffer = ""

    def feed(self, text: str) -> str:
        self._buffer += text
        out, self._buffer = self._split(self._buffer)
        return self._substitute(out)

    def flush(self) -> str:
        out, self._buffer = self._buffer, ""
        return self._substitute(out)

    @staticmethod
    def _split(text: str) -> tuple[str, str]:
        start = text.rfind("[")
        if start != -1:
            tail = text[start:]
            if re.fullmatch(r"\[\d{0,2}", tail):
                return text[:start], tail

        boundary = max(text.rfind(" "), text.rfind("\n"))
        if boundary == -1:
            return ("", text) if len(text) < 200 else (text, "")
        head, tail = text[: boundary + 1], text[boundary + 1 :]
        return head, tail

    def _substitute(self, text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            citation = self._registry.resolve(int(match.group(1)))
            return f"({citation})" if citation else match.group(0)

        return self._flag_raw_refs(CITATION_RE.sub(replace, text))

    def _flag_raw_refs(self, text: str) -> str:
        known = set(self._registry.paths) | self._registry.external_paths
        basenames = {p.rsplit("/", 1)[-1] for p in known}

        def check(match: re.Match[str]) -> str:
            path = match.group(1)
            if path in known:
                return match.group(0)

            if "/" not in path and path in basenames:
                return match.group(0)
            return f"{path} [unverified]"

        return RAW_REF_RE.sub(check, text)
