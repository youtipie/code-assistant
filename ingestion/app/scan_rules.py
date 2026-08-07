from __future__ import annotations

from pathlib import Path

LANGUAGES = {
    ".py": "python",
    ".md": "markdown",
    ".mdx": "markdown",
    ".graphql": "graphql",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
}

# Directories that would bloat the index without answering any question a
# human would ask. Migrations especially: thousands of generated files.
EXCLUDE_DIRS = {
    "tests",
    "test",
    "migrations",
    "__pycache__",
    "node_modules",
    ".git",
    "snapshots",
    "locale",
    "static",
    "fixtures",
}

MAX_FILE_BYTES = 400_000


def language_for(path: Path) -> str | None:
    return LANGUAGES.get(path.suffix.lower())


def is_excluded(rel: Path, exclude: tuple[str, ...]) -> bool:
    if EXCLUDE_DIRS & set(rel.parts):
        return True
    return any(str(rel).startswith(x) for x in exclude)


def size_in_bounds(size: int) -> bool:
    return 0 < size <= MAX_FILE_BYTES
