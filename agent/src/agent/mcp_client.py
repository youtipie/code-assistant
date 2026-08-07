from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.config import settings

from .interceptor import TurnInterceptor

log = logging.getLogger(__name__)

# bounds on the reconnect backoff in _retry_loop
RETRY_MIN = 2.0
RETRY_MAX = 60.0

_ENV_REF = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(value: str) -> str:
    import os

    return _ENV_REF.sub(lambda m: os.getenv(m.group(1), ""), value)


def _check_credentials(name: str, headers: dict[str, str]) -> None:
    auth = headers.get("Authorization", "")
    if not auth:
        return
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        log.warning("MCP %s: Authorization header is empty after expansion", name)
    elif any(c in token for c in ", \t\n"):
        log.warning(
            "MCP %s: token contains a comma or whitespace -- more than one value "
            "probably ended up in the variable. Expect a 400. (length %d)",
            name,
            len(token),
        )


def load_config() -> dict[str, dict]:
    import os

    path = Path(settings.mcp_config)
    if not path.exists():
        log.warning("no MCP config at %s", path.resolve())
        return {}

    servers: dict[str, dict] = {}
    for name, cfg in json.loads(path.read_text()).items():
        required = cfg.get("requires_env")
        if required and not os.getenv(required):
            log.info("MCP server %s skipped: %s is not set", name, required)
            continue
        headers = {k: _expand(v) for k, v in cfg.get("headers", {}).items()}
        _check_credentials(name, headers)
        servers[name] = {
            "url": _expand(cfg["url"]),
            "headers": headers,
            "description": cfg.get("description", ""),
        }
    return servers


@dataclass
class ServerState:
    name: str
    description: str
    tools: list[BaseTool] = field(default_factory=list)
    available: bool = False
    error: str | None = None


class MCPManager:
    def __init__(self) -> None:
        self._client: MultiServerMCPClient | None = None
        self._servers: dict[str, ServerState] = {}
        self._retry: asyncio.Task | None = None

    async def connect_all(self) -> None:
        """Connects to every configured MCP server and wires each tool call
        through agent's own `TurnInterceptor` -- agent owns interception end
        to end, so no caller needs to supply one.
        """
        config = load_config()
        if not config:
            return

        connections: dict[str, Any] = {
            name: {
                "transport": "streamable_http",
                "url": cfg["url"],
                **({"headers": cfg["headers"]} if cfg["headers"] else {}),
            }
            for name, cfg in config.items()
        }
        for name, cfg in config.items():
            self._servers[name] = ServerState(name=name, description=cfg["description"])
            if cfg["headers"]:
                log.info("MCP %s: headers %s", name, sorted(cfg["headers"]))

        self._client = MultiServerMCPClient(
            connections,
            tool_interceptors=[TurnInterceptor()],
            handle_tool_errors=True,
        )

        for name in config:
            await self._load(name)
        self._log_state()
        self._retry = asyncio.create_task(self._retry_loop(), name="mcp-retry")

    async def _load(self, name: str) -> bool:
        state = self._servers[name]
        assert self._client is not None
        try:
            state.tools = await self._client.get_tools(server_name=name)
        except Exception as exc:
            state.available = False
            if state.error != str(exc):
                log.warning("MCP %s unavailable: %s", name, exc)
            state.error = str(exc)
            return False

        state.available = True
        state.error = None
        log.info(
            "MCP %s connected: %d tools %s",
            name,
            len(state.tools),
            [t.name for t in state.tools],
        )
        return True

    async def _retry_loop(self) -> None:
        attempt = 0
        while True:
            # doubles per consecutive failure, capped; `attempt` is clamped
            # before exponentiation so a long failure streak can't overflow
            await asyncio.sleep(min(RETRY_MIN * 2 ** min(attempt, 64), RETRY_MAX))
            missing = self.unavailable
            if not missing:
                attempt = 0
                continue
            recovered = [name for name in missing if await self._load(name)]
            if recovered:
                log.info("MCP recovered: %s", recovered)
                self._log_state()
                attempt = 0
            else:
                attempt += 1

    async def close(self) -> None:
        if self._retry is not None:
            self._retry.cancel()
            await asyncio.gather(self._retry, return_exceptions=True)
            self._retry = None
        self._servers.clear()
        self._client = None

    def _log_state(self) -> None:
        available = [s.name for s in self._servers.values() if s.available]
        missing = self.unavailable
        log.info(
            "MCP: %d tools from %s%s",
            len(self.tools()),
            available or "no servers",
            f" (unavailable: {missing}, retrying)" if missing else "",
        )

    def tools(self) -> list[BaseTool]:
        return [t for s in self._servers.values() if s.available for t in s.tools]

    def server_of(self, tool_name: str) -> str:
        for state in self._servers.values():
            if any(t.name == tool_name for t in state.tools):
                return state.name
        return ""

    def active(self) -> list[tuple[str, str]]:
        return [(s.name, s.description) for s in self._servers.values() if s.available]

    @property
    def unavailable(self) -> list[str]:
        return [s.name for s in self._servers.values() if not s.available]


manager = MCPManager()
