"""Alembic migration environment — async-compatible.

Both deployment shapes (desktop SQLite + Docker PostgreSQL) share this file;
the DATABASE_URL is read from the app settings at runtime, so the CLI and the
launcher-driven path (`python -m db_migrations`) always migrate the same
database the app will use.
"""

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

_APP_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = _APP_ROOT / "api"
for _path in (_APP_ROOT, _API_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    # Prefer the live environment over the Settings singleton: launchers and
    # tests may set DATABASE_URL after Settings() was first instantiated.
    url = os.environ.get("DATABASE_URL")
    if not url:
        from utils import env  # noqa: PLC0415

        url = env.DATABASE_URL
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not configured: set it in .env or export it before running alembic"
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _database_url())
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
