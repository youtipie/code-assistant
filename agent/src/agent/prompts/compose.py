from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .text import NO_TOOLS_DIRECTIVE, REVIEW_GUIDANCE

if TYPE_CHECKING:
    # annotation only -- importing it for real would be circular, since
    # config reads DEFAULT_SYSTEM_PROMPT from this package
    from ..config import Settings


def compose_system_prompt(
    tools: list,
    finalising: bool,
    unavailable: list[str],
    active: list[tuple[str, str]],
    settings: Settings,
) -> str:
    prompt = settings.system_prompt

    if finalising or not tools:
        if not tools:
            prompt += "\n\n" + NO_TOOLS_DIRECTIVE
            if unavailable:
                prompt += (
                    "\nUnreachable tool servers: "
                    f"{', '.join(unavailable)}."
                )
        return prompt

    lines = [f"- {t.name}: {_summarise(t.description)}" for t in tools]
    prompt += "\n\nTools available right now:\n" + "\n".join(lines)

    if any(name == "github" for name, _ in active):
        prompt += "\n\n" + REVIEW_GUIDANCE

    if active:
        prompt += "\n\nTool servers:\n" + "\n".join(
            f"- {name}: {desc}" for name, desc in active if desc
        )

    if any(name == "github" for name, _ in active):
        mapping = "\n".join(
            f"- {prefix or '(default)'} -> {repo}"
            for repo, prefix in settings.corpus_repos
        )
        prompt += (
            "\n\nThe indexed corpus spans more than one repository:\n"
            f"{mapping}\n"
            "Live queries are scoped to the right one automatically from the "
            "path you pass, so use the exact path from a citation. Issues and "
            f"pull requests live in {settings.corpus_repo}.\n"
            "The snapshot is pinned at one commit and may be behind. Questions "
            "about history, recent changes, who changed something, pull "
            "requests, issues, or whether the live code still matches the docs "
            "cannot be answered from the snapshot -- call a github tool. "
            "Saying the code 'still matches' without having fetched it is "
            "wrong even when the conclusion happens to be right."
        )
    if unavailable:
        prompt += (
            "\n\nSome tool servers are unreachable this session: "
            f"{', '.join(unavailable)}. Their capabilities are gone; "
            "say so if the answer needs one."
        )
    return prompt


def _summarise(description: str | None, limit: int = 160) -> str:
    text = " ".join((description or "").split())
    if not text:
        return ""
    match = re.search(r"(?<=[.!?])\s", text)
    sentence = text[: match.start()] if match else text
    return sentence if len(sentence) <= limit else sentence[: limit - 1] + "…"
