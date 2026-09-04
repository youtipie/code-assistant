"""Run the scope gate over `evals/scope_cases.yaml` and report what it got wrong.

    uv run evals/scope.py            # the whole set
    uv run evals/scope.py --verbose  # every case, not just the failures

Needs OPENAI_API_KEY and nothing else -- no database, no index, no running
gateway. Exits non-zero when a case disagrees with its expectation, so it can
gate a change to the classifier prompt.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from agent.config import settings
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from agent import scope

CASES = Path(__file__).resolve().parent / "scope_cases.yaml"


@dataclass
class Case:
    question: str
    expect_allowed: bool
    history: list[BaseMessage]

    @property
    def label(self) -> str:
        return f"{self.question[:60]}{'…' if len(self.question) > 60 else ''}"


def load(path: Path) -> list[Case]:
    cases = []
    for item in yaml.safe_load(path.read_text()):
        history: list[BaseMessage] = []
        for exchange in item.get("after") or []:
            history.append(HumanMessage(content=exchange["user"]))
            history.append(AIMessage(content=exchange["assistant"]))
        cases.append(
            Case(
                question=item["q"],
                expect_allowed=item["expect"] == "allow",
                history=history,
            )
        )
    return cases


async def main(verbose: bool) -> int:
    if not settings.openai_api_key:
        print("OPENAI_API_KEY is not set", file=sys.stderr)
        return 2
    # measures the gate even where it is deployed switched off
    on = settings.model_copy(update={"scope_guard_enabled": True})

    cases = load(CASES)
    verdicts = await asyncio.gather(
        *(scope.check(case.question, case.history, on) for case in cases)
    )

    wrong = spend = 0
    for case, verdict in zip(cases, verdicts, strict=True):
        spend += verdict.cost_usd or 0.0
        ok = verdict.allowed is case.expect_allowed
        wrong += not ok
        if verbose or not ok:
            got = "allow" if verdict.allowed else "refuse"
            want = "allow" if case.expect_allowed else "refuse"
            mark = "ok  " if ok else "FAIL"
            print(f"{mark}  got {got:<6} want {want:<6}  {case.label}")
            # allowed without running is an unreachable classifier, not a
            # misjudged question
            if not verdict.ran:
                print("      (gate did not run -- classifier unreachable?)")

    print(
        f"\n{len(cases) - wrong}/{len(cases)} as expected "
        f"({settings.scope_model}, ${spend:.4f})"
    )
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--verbose" in sys.argv or "-v" in sys.argv)))
