"""Settings, FastMCP wiring and uvicorn startup for the knowledge server.

The tools themselves are in `tools.py` and their queries in `queries.py`;
this module only wires them up and serves them.
"""

from __future__ import annotations

import logging

from core.db import close_db, open_db
from core.settings import BaseAppSettings, CommaSeparated, core_settings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from .tools import TOOLS


class ServerSettings(BaseAppSettings):
    port: int = 8080
    allowed_hosts: CommaSeparated = Field(
        default=["knowledge:8080", "localhost:8080", "127.0.0.1:8080"],
        alias="MCP_ALLOWED_HOSTS",
    )


server_settings = ServerSettings()

logging.basicConfig(
    level=core_settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("knowledge")

server = FastMCP(
    name="knowledge",
    instructions=(
        "Retrieval over an indexed codebase and its documentation. "
        "Search first, then read what the search points at."
    ),
)

# registered explicitly rather than by decorator, so the tool list is visible
# in one place and tools.py stays directly callable
for tool in TOOLS:
    server.tool()(tool)


@server.custom_route("/health", methods=["GET"])
async def health(_request):
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok", "server": "knowledge"})


def main() -> None:
    import asyncio

    import uvicorn

    async def run() -> None:
        await open_db()
        try:
            # DNS-rebinding protection trusts only localhost by default, so
            # inside compose every request arrives with Host: knowledge:8080
            # and is rejected with 421. Trust the service names we actually
            # serve; MCP_ALLOWED_HOSTS widens it for other deployments.
            allowed = server_settings.allowed_hosts
            server.settings.transport_security = TransportSecuritySettings(
                allowed_hosts=allowed,
                allowed_origins=allowed + [f"http://{h}" for h in allowed],
            )
            log.info("trusting Host headers: %s", allowed)

            config = uvicorn.Config(
                server.streamable_http_app(),
                host="0.0.0.0",
                port=server_settings.port,
                log_level=core_settings.log_level.lower(),
            )
            log.info("knowledge MCP server listening")
            await uvicorn.Server(config).serve()
        finally:
            await close_db()

    asyncio.run(run())


if __name__ == "__main__":
    main()
