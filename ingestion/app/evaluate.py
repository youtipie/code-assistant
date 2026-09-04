from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, stdev

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

# 95%, two-sided
Z = 1.96


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
    # distinct paths, in the order search returned them: relevance here is a
    # property of a file, so a file that takes two of the top slots with two
    # of its chunks is still one answer to have found. Keeping the duplicate
    # would also disagree with `_to_ranx`, which cannot hold a path twice.
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

        result = Result(
            item["q"], item["expect"], list(dict.fromkeys(h.path for h in hits))
        )
        results.append(result)

        rank = result.rank
        hit = rank is not None and rank <= 5
        if verbose or not hit:
            mark = "ok " if hit else "MISS"
            print(f"{mark} [{str(rank or '-'):>2}] {item['q']}")
        if not hit:
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


def _wilson(hits: int, total: int) -> tuple[float, float]:
    """95% interval for a proportion. Wilson rather than the textbook normal
    approximation because the scores that matter here sit near 1.0, where the
    normal one runs off the end of the scale and claims 1.02."""
    if not total:
        return 0.0, 0.0
    proportion = hits / total
    denominator = 1 + Z**2 / total
    centre = (proportion + Z**2 / (2 * total)) / denominator
    spread = (
        Z
        * math.sqrt(
            proportion * (1 - proportion) / total + Z**2 / (4 * total**2)
        )
        / denominator
    )
    return max(0.0, centre - spread), min(1.0, centre + spread)


def _mean_interval(values: list[float]) -> tuple[float, float]:
    """95% interval for a mean -- MRR is an average of reciprocal ranks, not a
    proportion, so it gets the ordinary standard error of the mean."""
    if len(values) < 2:
        return (values[0], values[0]) if values else (0.0, 0.0)
    spread = Z * stdev(values) / math.sqrt(len(values))
    mean = fmean(values)
    return max(0.0, mean - spread), min(1.0, mean + spread)


def _interval(metric: str, results: list[Result]) -> tuple[float, float]:
    if metric.startswith("hit_rate@"):
        k = int(metric.split("@")[1])
        return _wilson(
            sum(1 for r in results if r.rank and r.rank <= k), len(results)
        )
    return _mean_interval([1 / r.rank if r.rank else 0.0 for r in results])


def report(results: list[Result], label: str = "") -> dict[str, float]:
    if not results:
        return {}

    qrels, run = _to_ranx(results)
    scores = {k: float(v) for k, v in evaluate(qrels, run, METRICS).items()}

    header = f"{label} " if label else ""
    table = Table(title=f"{header}{len(results)} questions", title_justify="left")
    table.add_column("metric")
    table.add_column("score", justify="right")
    # what the set can and cannot tell apart. The first thing anyone does with
    # an eval is compare two runs of it and the second is over-read the
    # difference; on 25 questions one item flipping was worth four points.
    table.add_column("95% CI", justify="right")
    table.add_column("")
    for name, value in scores.items():
        low, high = _interval(name, results)
        table.add_row(
            name,
            f"{value:.2f}",
            f"{low:.2f}–{high:.2f}",
            ProgressBar(total=1.0, completed=value, width=30),
        )
    Console().print(table)

    misses = [r for r in results if not r.rank or r.rank > 5]
    if misses:
        print(f"\n  {len(misses)} outside top 5:")
        for result in misses:
            print(f"    - {result.question}  (rank {result.rank or 'none'})")
    return scores
