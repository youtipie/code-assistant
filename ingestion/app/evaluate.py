from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from core.db import session
from core.embedding import embed_query
from core.retrieval.search import search
from ranx import Qrels, Run, evaluate
from rich.console import Console
from rich.progress_bar import ProgressBar
from rich.table import Table

log = logging.getLogger("eval")

METRICS = ["hit_rate@1", "hit_rate@3", "hit_rate@5", "hit_rate@10", "mrr"]


def _default_set() -> Path:
    here = Path(__file__).resolve()
    for candidate in (
        here.parents[2] / "evals" / "questions.yaml",
        here.parents[3] / "evals" / "questions.yaml",
        Path("evals/questions.yaml"),
    ):
        if candidate.exists():
            return candidate
    return here.parents[2] / "evals" / "questions.yaml"


@dataclass
class Result:
    question: str
    expected: list[str]
    ranked: list[str]

    @property
    def rank(self) -> int | None:
        return next(
            (i for i, path in enumerate(self.ranked, 1) if path in self.expected),
            None,
        )


async def run_eval(
    path: Path | None = None,
    limit: int = 10,
    verbose: bool = False,
) -> list[Result]:
    questions = yaml.safe_load((path or _default_set()).read_text())
    results: list[Result] = []

    for item in questions:
        source_type = item.get("type")
        vector = embed_query(item["q"])
        async with session() as db:
            hits = await search(
                db,
                item["q"],
                vector,
                limit=limit,
                source_type=None if source_type == "any" else source_type,
            )

        result = Result(item["q"], item["expect"], [h.path for h in hits])
        results.append(result)

        if verbose:
            rank = result.rank
            mark = "ok " if rank and rank <= 5 else "MISS"
            print(f"{mark} [{str(rank or '-'):>2}] {item['q']}")
            if not rank or rank > 5:
                print(f"       expected: {', '.join(result.expected)}")
                for i, path_ in enumerate(result.ranked[:5], 1):
                    print(f"       {i}. {path_}")

    return results


def _to_ranx(results: list[Result]) -> tuple[Qrels, Run]:
    qrels: dict[str, dict[str, int]] = {}
    run: dict[str, dict[str, float]] = {}
    for i, result in enumerate(results):
        query_id = f"q{i}"
        qrels[query_id] = dict.fromkeys(result.expected, 1)
        run[query_id] = {
            path: 1.0 / position
            for position, path in enumerate(result.ranked, 1)
        }
        if not run[query_id]:
            run[query_id] = {"__none__": 0.0}
    return Qrels(qrels), Run(run)


def report(results: list[Result], label: str = "") -> dict[str, float]:
    if not results:
        return {}

    qrels, run = _to_ranx(results)
    scores = {k: float(v) for k, v in evaluate(qrels, run, METRICS).items()}

    header = f"{label} " if label else ""
    table = Table(title=f"{header}{len(results)} questions", title_justify="left")
    table.add_column("metric")
    table.add_column("score", justify="right")
    table.add_column("")
    for name, value in scores.items():
        table.add_row(
            name, f"{value:.2f}", ProgressBar(total=1.0, completed=value, width=30)
        )
    Console().print(table)

    misses = [r for r in results if not r.rank or r.rank > 5]
    if misses:
        print(f"\n  {len(misses)} outside top 5:")
        for result in misses:
            print(f"    - {result.question}  (rank {result.rank or 'none'})")
    return scores
