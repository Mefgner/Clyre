import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models import Base
from utils import cfg, env

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)


class SessionManager:
    def __init__(self, echo: bool = False):
        Logger.info("Initializing database engine")
        self._db_base = f"{env.DB_ENGINE}+{env.DB_RUNTIME}://"
        if env.DB_ENGINE == "sqlite":
            self._db_base += "/"
        self._db_url = f"{self._db_base}{cfg.get_resolved_db_path().as_posix()}"
        self._engine: AsyncEngine = create_async_engine(self._db_url, echo=echo, future=True)
        self._session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def init_models(self):
        async with self._engine.begin() as conn:
            Logger.info("Creating database tables")
            await conn.run_sync(Base.metadata.create_all)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_maker(self) -> async_sessionmaker[AsyncSession]:
        return self._session_maker

    @property
    @asynccontextmanager
    async def context_manager(self) -> AsyncIterator[AsyncSession]:
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


sm_instance: SessionManager | None = None


def get_session_manager() -> SessionManager:
    Logger.debug("Getting session manager")
    global sm_instance
    if not sm_instance:
        Logger.debug("Creating new session manager")
        sm_instance = SessionManager()
    return sm_instance
