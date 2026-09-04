"""The scope gate: one cheap model call, before the graph, that decides
whether a question is about the corpus at all.

The system prompt states the same rule, but a prompt can be argued with, and
finding out that it lost costs a full turn with tools. The gate fails open and
is biased towards allowing: a wrongly refused question looks broken, while a
wrongly admitted one still meets the agent's own "not in the indexed corpus".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from core.pricing import cost_usd
from core.settings import core_settings
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import Settings
from .prompts.text import SCOPE_CLASSIFIER_PROMPT

log = logging.getLogger(__name__)

# A follow-up ("why?") is only classifiable against what it follows, so the
# gate sees the tail of the thread -- bounded, because it must not cost more
# than it guards.
HISTORY_MESSAGES = 6
HISTORY_CHARS = 300

# The gate is on the latency of every turn, and failure allows the question
# through anyway, so waiting longer buys nothing.
MAX_TOKENS = 16
TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 1


@dataclass
class Verdict:
    """The gate's answer, plus what asking cost. `ran` separates "allowed by
    the classifier" from "allowed because the gate is off or unreachable"."""

    allowed: bool
    ran: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None


_model: ChatOpenAI | None = None


async def check(
    question: str, history: list[BaseMessage], settings: Settings
) -> Verdict:
    """Classify `question` against the corpus, in the context of `history`."""
    if not settings.scope_guard_enabled or not question.strip():
        return Verdict(allowed=True)

    messages = [
        SystemMessage(
            content=SCOPE_CLASSIFIER_PROMPT.format(corpus=settings.corpus_name)
        ),
        HumanMessage(content=_render(question, history)),
    ]
    try:
        response = await _classifier(settings).ainvoke(messages)
    except Exception:
        log.warning("scope gate unavailable, allowing the question", exc_info=True)
        return Verdict(allowed=True)

    usage = getattr(response, "usage_metadata", None) or {}
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)
    allowed = _allowed(_text_of(response))
    if not allowed:
        log.info("scope gate refused a question")
    return Verdict(
        allowed=allowed,
        ran=True,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd(
            settings.scope_model,
            prompt_tokens,
            completion_tokens,
            table=core_settings.prices,
        ),
    )


def _allowed(verdict: str) -> bool:
    """Anything but a clear OUT_OF_SCOPE is allowed: an unrecognised answer is
    not evidence that the question was off topic."""
    return not re.sub(r"[^A-Z]", "", verdict.upper()).startswith("OUTOFSCOPE")


def _render(question: str, history: list[BaseMessage]) -> str:
    lines = []
    if turns := _recent(history):
        lines.append("<conversation_so_far>")
        lines.extend(turns)
        lines.append("</conversation_so_far>\n")
    lines.append("<message_to_classify>")
    lines.append(_clip(question, HISTORY_CHARS * 2))
    lines.append("</message_to_classify>")
    return "\n".join(lines)


def _recent(history: list[BaseMessage]) -> list[str]:
    turns: list[str] = []
    for message in reversed(history):
        if len(turns) >= HISTORY_MESSAGES:
            break
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage) and not message.tool_calls:
            role = "assistant"
        else:
            # tool results are third-party text the classifier should not read
            continue
        if text := _clip(_text_of(message), HISTORY_CHARS):
            turns.append(f"{role}: {text}")
    return list(reversed(turns))


def _clip(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def _text_of(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _classifier(settings: Settings) -> ChatOpenAI:
    """A reasoning model configured here would spend the whole output budget
    thinking and return nothing parseable -- which fails open, loudly."""
    global _model
    if _model is None:
        _model = ChatOpenAI(
            model=settings.scope_model,
            api_key=settings.openai_api_key,
            temperature=0,
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT_SECONDS,
            max_retries=MAX_RETRIES,
        )
    return _model
