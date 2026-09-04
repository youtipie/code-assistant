from __future__ import annotations

from dataclasses import dataclass

from .agent import run_turn
from .config import settings as _settings
from .graph import build_graph, close_graph
from .mcp_client import manager as _manager

connect_mcp = _manager.connect_all
close_mcp = _manager.close

# the configured model name, for callers that need only this and not the full
# status() snapshot (which walks every MCP tool to build it)
openai_model: str = _settings.openai_model


@dataclass
class AgentStatus:
    tools: list[str]
    tools_per_server: dict[str, int]
    active_servers: list[tuple[str, str]]
    unavailable_servers: list[str]
    openai_model: str
    corpus_repos: list[tuple[str, str]]


def status() -> AgentStatus:
    """Plain-data snapshot of MCP/model state for gateway's /status endpoint,
    so no caller has to reach into the manager singleton or the settings."""
    tools = _manager.tools()
    per_server: dict[str, int] = {}
    for tool in tools:
        server = _manager.server_of(tool.name)
        per_server[server] = per_server.get(server, 0) + 1
    return AgentStatus(
        tools=[t.name for t in tools],
        tools_per_server=per_server,
        active_servers=_manager.active(),
        unavailable_servers=_manager.unavailable,
        openai_model=_settings.openai_model,
        corpus_repos=_settings.corpus_repos,
    )


__all__ = [
    "AgentStatus",
    "build_graph",
    "close_graph",
    "close_mcp",
    "connect_mcp",
    "openai_model",
    "run_turn",
    "status",
]
