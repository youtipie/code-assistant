"""The ingestion CLI: five commands over the modules around it.

Command bodies are plain async functions; the @command decorator handles the
shared logging setup and database lifecycle.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import subprocess
from pathlib import Path

import typer
from core.db import close_db, open_db

from .collect import collect_corpus
from .evaluate import report, run_eval
from .pipeline import chunk_all, load_documents, prune, run_search
from .report import summarise
from .sources import SOURCES

log = logging.getLogger("ingest")

app = typer.Typer(
    add_completion=False,
    help="Clone, index and query the corpus. No API calls: embeddings are local.",
)


# Set by the callback below before any command body runs. None means "the
# command picks" -- the reporting commands default quieter than the indexing
# ones, so their output is not buried in progress logging.
_log_level: str | None = None


@app.callback()
def _configure(
    log_level: str | None = typer.Option(None, help="Python logging level."),
) -> None:
    global _log_level
    _log_level = log_level


def command(name: str | None = None, *, level: str = "INFO", db: bool = True):
    """Register a command, configure logging, and -- unless db=False -- open
    and close the database around it. The body is an async function; every
    command is async and every one but `scan` needs the engine."""

    def decorator(fn):
        @app.command(name or fn.__name__)
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            logging.basicConfig(
                level=(_log_level or level).upper(),
                format="%(levelname)s %(name)s %(message)s",
            )

            async def run():
                if not db:
                    return await fn(*args, **kwargs)
                await open_db()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    await close_db()

            asyncio.run(run())

        return wrapper

    return decorator


@command(db=False)
async def scan(
    rev: str | None = typer.Option(None, help="Pin to a specific commit sha."),
) -> None:
    summarise(await collect_corpus(rev))


@command()
async def load(
    rev: str | None = typer.Option(None, help="Pin to a specific commit sha."),
) -> None:
    records = await collect_corpus(rev)
    summarise(records)
    written, skipped = await load_documents(records)
    removed = 0
    for source in SOURCES:
        paths = [r.path for r in records if r.repo == source.repo]
        removed += await prune(source.repo, paths)
    print(f"\nwritten/updated {written}, unchanged {skipped}, pruned {removed}")


@command()
async def chunk(
    force: bool = typer.Option(False, help="Re-chunk documents that have not changed."),
) -> None:
    written, skipped, docs = await chunk_all(force=force)
    print(f"\n{written} chunks from {docs} documents, {skipped} documents unchanged")


@command("search", level="WARNING")
async def search_corpus(
    query: str = typer.Argument(..., help="What to look for."),
    limit: int = typer.Option(8, "--limit", "-k", help="How many hits to show."),
    source_type: str | None = typer.Option(
        None, "--type", help="Restrict to 'code' or 'doc'."
    ),
) -> None:
    await run_search(query, limit, source_type)


@command("eval", level="WARNING")
async def evaluate(
    questions: Path | None = typer.Option(
        None, help="Question set (default evals/questions.yaml)."
    ),
    limit: int = typer.Option(10, "--limit", "-k", help="Depth to retrieve."),
) -> None:
    report(await run_eval(questions, limit=limit, verbose=True))


def main() -> None:
    try:
        app()
    except subprocess.CalledProcessError as exc:
        log.error("git failed: %s", exc)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    main()
