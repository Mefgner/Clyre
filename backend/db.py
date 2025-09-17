from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from models import Base
from utils import cfg


class SessionManager:
    def __init__(self, echo: bool = False):
        self._db_base = f"{cfg.get_db_engine()}+{cfg.get_db_runtime()}://"
        if cfg.get_db_engine() == 'sqlite':
            self._db_base += '/'
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
            await conn.run_sync(Base.metadata.create_all)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_maker(self) -> async_sessionmaker[AsyncSession]:
        return self._session_maker

    @asynccontextmanager
    async def get_session_context_manager(self) -> AsyncIterator[AsyncSession]:
        async with self._session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


sm_instance: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global sm_instance
    if not sm_instance:
        sm_instance = SessionManager()
    return sm_instance
