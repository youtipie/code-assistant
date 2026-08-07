"""Getting the corpus onto disk and into memory: clone, walk, classify.

No database here -- `collect` returns plain FileRecords and `persistence`
decides what to do with them.
"""

from __future__ import annotations

import ast
import hashlib
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .scan_rules import is_excluded, language_for, size_in_bounds
from .sources import SOURCES, Source

log = logging.getLogger("ingest")



@dataclass
class FileRecord:
    source_type: str
    repo: str
    commit_sha: str
    path: str
    language: str
    content: str
    content_hash: str
    size_bytes: int
    line_count: int
    symbol_count: int


def clone(source: Source, dest: Path, rev: str | None) -> str:
    log.info("cloning %s", source.repo)
    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", source.url, str(dest)],
        check=True,
    )
    if rev:
        subprocess.run(
            ["git", "fetch", "--depth", "1", "--quiet", "origin", rev],
            cwd=dest,
            check=True,
        )
        subprocess.run(["git", "checkout", "--quiet", rev], cwd=dest, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=dest,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    log.info("%s pinned at %s", source.repo, sha[:12])
    return sha


def count_python_symbols(text: str) -> int:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 0
    return sum(
        isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        for n in ast.walk(tree)
    )


def collect(source: Source, root: Path, sha: str) -> list[FileRecord]:
    roots = [root / p for p in source.paths] if source.paths else [root]
    records: list[FileRecord] = []

    for scope in roots:
        if not scope.exists():
            log.warning("missing path %s in %s", scope.name, source.repo)
            continue

        for path in sorted(scope.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if is_excluded(rel, source.exclude):
                continue

            language = language_for(path)
            if language is None:
                continue

            size = path.stat().st_size
            if not size_in_bounds(size):
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            records.append(
                FileRecord(
                    source_type=source.source_type,
                    repo=source.repo,
                    commit_sha=sha,
                    path=str(path.relative_to(root)),
                    language=language,
                    content=text,
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    size_bytes=size,
                    line_count=text.count("\n") + 1,
                    symbol_count=(
                        count_python_symbols(text) if language == "python" else 0
                    ),
                )
            )
    return records

async def collect_corpus(rev: str | None) -> list[FileRecord]:
    """Clone every source into a scratch directory, collect from it, and throw
    the clone away -- nothing downstream needs the working tree."""
    workdir = Path(tempfile.mkdtemp(prefix="corpus-"))
    records: list[FileRecord] = []
    try:
        for source in SOURCES:
            dest = workdir / source.repo.replace("/", "__")
            sha = clone(source, dest, rev)
            found = collect(source, dest, sha)
            log.info("%s: %d files", source.repo, len(found))
            records.extend(found)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        log.info("clone discarded")
    return records
