from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from core.models import Base
from core.settings import core_settings
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
config.set_main_option("sqlalchemy.url", core_settings.async_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=core_settings.async_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def render_item(type_: str, obj: object, autogen_context) -> str | bool:
    """Make autogenerate emit the pgvector import it otherwise forgets."""
    if type_ == "type" and obj.__class__.__module__.startswith("pgvector"):
        autogen_context.imports.add("import pgvector.sqlalchemy")
    return False


# LangGraph creates and owns these through its own setup(); they are not in
# our metadata, so autogenerate reads them as tables to drop. Losing them would
# delete every conversation's state.
EXTERNAL_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def include_object(obj, name, type_, _reflected, _compare_to) -> bool:
    if type_ == "table" and name in EXTERNAL_TABLES:
        return False
    if type_ == "index" and getattr(obj, "table", None) is not None:
        return obj.table.name not in EXTERNAL_TABLES
    return True


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_item=render_item,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
