from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .settings import core_settings

log = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("engine not initialised; call open_db() first")
    return _engine


async def open_db(echo: bool = False) -> AsyncEngine:
    global _engine, _sessionmaker
    _engine = create_async_engine(
        core_settings.async_database_url,
        echo=echo,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
    )
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    log.info("database engine ready")
    return _engine


async def close_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("engine not initialised; call open_db() first")
    async with _sessionmaker() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise
