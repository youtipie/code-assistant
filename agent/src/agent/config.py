from __future__ import annotations

from pathlib import Path

from core.settings import BaseAppSettings
from pydantic import Field, field_validator

from .prompts.text import DEFAULT_SYSTEM_PROMPT

_DEFAULT_MCP_CONFIG = str(
    Path(__file__).resolve().parent.parent.parent / "mcp_servers.json"
)


class Settings(BaseAppSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"

    openai_use_responses_api: bool = True
    openai_reasoning_effort: str = ""

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    mcp_config: str = _DEFAULT_MCP_CONFIG

    # "owner/repo=path/prefix/" pairs, parsed once at load rather than on
    # every access -- repo_for_path walks the whole list per tool call.
    corpus_repos: list[tuple[str, str]] = Field(
        default="saleor/saleor=saleor/,saleor/saleor-docs=docs/",
        alias="CORPUS_REPOS",
    )

    @field_validator("openai_reasoning_effort")
    @classmethod
    def _known_effort(cls, value: str) -> str:
        allowed = {"", "none", "minimal", "low", "medium", "high"}
        if value.strip().lower() not in allowed:
            raise ValueError(f"expected one of {sorted(allowed - {''})}, got {value!r}")
        return value.strip().lower()

    @field_validator("corpus_repos", mode="before")
    @classmethod
    def _parse_repos(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        pairs: list[tuple[str, str]] = []
        for entry in value.split(","):
            repo, _, prefix = entry.strip().partition("=")
            if repo:
                pairs.append((repo.strip(), prefix.strip()))
        return pairs

    @property
    def corpus_repo(self) -> str:
        return self.corpus_repos[0][0] if self.corpus_repos else "saleor/saleor"

    def repo_for_path(self, path: str) -> str:
        best = ""
        chosen = self.corpus_repo
        for repo, prefix in self.corpus_repos:
            if prefix and path.startswith(prefix) and len(prefix) > len(best):
                best, chosen = prefix, repo
        return chosen


settings = Settings()
