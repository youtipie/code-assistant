"""The FastAPI app: lifespan, middleware, health, and route wiring.

The websocket receive loop and turn persistence live in `ws/`; the REST
endpoints in `api.py`.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from core.db import close_db, open_db, session
from core.settings import core_settings
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from agent import build_graph, close_graph, close_mcp, connect_mcp, openai_model

from .api import router as api_router
from .config import settings
from .tracing import setup_tracing, shutdown_tracing
from .ws import chat as chat_loop
from .ws import persists

logging.basicConfig(
    level=core_settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# langchain-mcp-adapters binds tools to a *connection*, so every tool call
# opens and closes its own MCP session, and each close logs "GET stream
# disconnected, reconnecting..." at INFO -- ~90 times in a thorough turn, and
# nothing like the client disconnect it reads as. Warnings still get through.
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)

log = logging.getLogger("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # before build_graph(): instrumenting LangChain patches machinery the
    # graph is about to construct
    setup_tracing()
    await open_db()
    await connect_mcp()
    await build_graph()
    yield
    await close_graph()
    await close_mcp()
    await persists.drain()
    await close_db()
    # last: the span batch has to flush before the process goes away
    shutdown_tracing()


app = FastAPI(title="AI Engineering Assistant Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    async with session() as db:
        await db.execute(text("SELECT 1"))
    return {"status": "ok", "model": openai_model}


@app.websocket("/chat")
async def chat(ws: WebSocket, client: str | None = None) -> None:
    await chat_loop(ws, client)
