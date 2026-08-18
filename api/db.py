import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from utils import env

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)


def register_sqlite_vec(engine: AsyncEngine) -> None:
    import sqlite_vec

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, _record):
        # aiosqlite opens the raw sqlite3 connection with check_same_thread=False,
        # so loading the extension from the event thread is safe.
        raw = getattr(dbapi_connection, "driver_connection", dbapi_connection)
        raw = getattr(raw, "_conn", raw)
        raw.enable_load_extension(True)
        sqlite_vec.load(raw)
        raw.enable_load_extension(False)
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA journal_mode=WAL")


class AsyncSessionManager:
    def __init__(self, echo: bool = False):
        Logger.info("Initializing database engine")
        self._db_url = env.DATABASE_URL

        if not self._db_url:
            raise ValueError("DATABASE_URL is not configured")

        self._engine: AsyncEngine = create_async_engine(self._db_url, echo=echo, future=True)

        if env.DB_ENGINE == "sqlite":
            register_sqlite_vec(self._engine)

        self._session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    @property
    def async_engine(self) -> AsyncEngine:
        return self._engine

    @property
    def async_session_maker(self) -> async_sessionmaker[AsyncSession]:
        return self._session_maker

    @property
    @asynccontextmanager
    async def async_session_context_manager(self) -> AsyncIterator[AsyncSession]:
        Logger.debug("Creating database session")
        async with self._session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self):
        Logger.info("Closing database engine")
        await self._engine.dispose()


sm_instance: AsyncSessionManager | None = None


def get_session_manager() -> AsyncSessionManager:
    Logger.debug("Getting session manager")
    global sm_instance
    if not sm_instance:
        Logger.info("Creating new session manager")
        sm_instance = AsyncSessionManager()
    return sm_instance


async def get_db_session() -> AsyncIterator[AsyncSession]:
    sm = get_session_manager()
    Logger.debug("Creating database session for request")
    async with sm.async_session_maker() as session:
        yield session
