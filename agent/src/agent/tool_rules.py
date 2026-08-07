from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Settings
from .knowledge import OWN_SERVER, READ_FILE, SEARCH_TOOLS

log = logging.getLogger(__name__)

MAX_READS_PER_PATH = 3
DIFF_METHODS = ("get_diff", "get", "get_reviews")


@dataclass
class Decision:
    args: dict
    refusal: str | None = None
    # the ToolResult preview when refusing -- distinct from `refusal`, which
    # is the message sent back to the model as the tool's own output
    refusal_preview: str | None = None
    # a key the caller should add to its `seen` set on allow, if any -- kept
    # out of this function so `decide()` only reads `seen`, never mutates it
    record: str | None = None


def decide(
    server: str,
    name: str,
    args: dict,
    seen: set[str],
    settings: Settings,
) -> Decision:
    args = dict(args)

    if server != OWN_SERVER:
        args = _scope_to_corpus(args, settings)
        if refusal := _refuse_fake_pagination(name, args):
            return Decision(args=args, refusal=refusal, refusal_preview="refused")
    elif server == OWN_SERVER:
        refusal, record = _refuse_repeat(name, args, seen)
        if refusal:
            return Decision(
                args=args, refusal=refusal, refusal_preview="repeat refused"
            )
        return Decision(args=args, record=record)

    return Decision(args=args)


def _scope_to_corpus(arguments: dict, settings: Settings) -> dict:
    path = arguments.get("path")
    known_path = isinstance(path, str) and any(
        prefix and path.startswith(prefix) for _, prefix in settings.corpus_repos
    )
    repo = settings.repo_for_path(path) if known_path else settings.corpus_repo
    owner, _, name = repo.partition("/")

    if known_path:
        if arguments.get("repo") not in (None, name):
            log.info(
                "scoping %s to %s (model asked for %s)",
                path, repo, arguments["repo"],
            )
        arguments["owner"] = owner
        arguments["repo"] = name
    else:
        arguments.setdefault("owner", owner)
        arguments.setdefault("repo", name)

    for key in ("query", "q"):
        value = arguments.get(key)
        if isinstance(value, str) and not any(
            marker in value for marker in ("repo:", "org:", "user:")
        ):
            arguments[key] = f"repo:{settings.corpus_repo} {value}".strip()
    return arguments


def _refuse_fake_pagination(name: str, arguments: dict) -> str | None:
    if name != "pull_request_read":
        return None
    page = arguments.get("page")
    if arguments.get("method") in DIFF_METHODS and isinstance(page, int) and page > 1:
        return (
            f"pull_request_read method={arguments.get('method')!r} does not "
            "paginate: `page` is accepted and ignored, so this would return the "
            "same content again. Use method='get_files' for the full file list, "
            "then get_file_contents on the ones that matter."
        )
    return None


def _refuse_repeat(
    name: str, arguments: dict, seen: set[str]
) -> tuple[str | None, str | None]:
    """Returns `(refusal, record)`. `record` is the key the caller should add
    to `seen` on allow; never both `refusal` and `record` at once."""
    if name in SEARCH_TOOLS:
        key = f"{name}:{str(arguments.get('query', '')).strip().lower()}"
        if key in seen:
            return (
                "You already ran this exact search in this turn and the results "
                "were identical. Do not repeat it. Read one of the passages you "
                "already have, try a materially different query, or answer now "
                "-- including saying the corpus does not cover it.",
                None,
            )
        return None, key

    if name == READ_FILE:
        path = arguments.get("path", "")
        symbol = arguments.get("symbol")
        if symbol:
            key = f"readsym:{path}:{str(symbol).strip().lower()}"
            if key in seen:
                return (
                    f"You already read {symbol} from {path} this turn -- the "
                    "result is identical. If it was truncated, continue from the "
                    "line number given. Otherwise answer with what you have.",
                    None,
                )
            return None, key

        reads = sum(1 for k in seen if k.startswith(f"readpos:{path}:"))
        if reads >= MAX_READS_PER_PATH:
            return (
                f"You have read {path} {reads} times this turn. Stop paging "
                "through it. Call outline(path) to see its structure, use "
                "search_code for a different file, or answer with what you have.",
                None,
            )
        return (
            None,
            f"readpos:{path}:{arguments.get('start_line')}:{arguments.get('end_line')}",
        )
    return None, None
