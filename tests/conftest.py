import os
import tempfile
import uuid

# Force a small, isolated SQLite config before any api module imports Settings().
os.environ["DB_ENGINE"] = "sqlite"
os.environ["VECTOR_DIM"] = "8"
os.environ["NORMALIZE_VECTORS"] = "true"
os.environ.setdefault("HASHING_SECRET", "test")
os.environ.setdefault("ACCESS_TOKEN_SECRET", "test")
os.environ.setdefault("REFRESH_TOKEN_SECRET", "test")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crud.vector import SqliteVecRepository
from db import register_sqlite_vec
from models import Base, ChunkVector, FileMetadata, User
from schemas.file import ChunkEmbedding

DIM = 8


@pytest_asyncio.fixture
async def engine():
    path = os.path.join(tempfile.gettempdir(), f"clyre_test_{uuid.uuid4().hex}.sqlite3")
    eng = create_async_engine(f"sqlite+aiosqlite:///{path}")
    register_sqlite_vec(eng)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await SqliteVecRepository().ensure_schema(eng)
    try:
        yield eng
    finally:
        await eng.dispose()
        for p in (path, path + "-wal", path + "-shm"):
            if os.path.exists(p):
                os.remove(p)


@pytest_asyncio.fixture
async def session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest.fixture
def repo():
    return SqliteVecRepository()


@pytest.fixture
def seeder(session, repo):
    """Returns an async callable that creates user + file + chunk_vector rows and
    writes their embeddings through the repo. Returns the new file_id."""

    async def _seed(workspace_id, chunks, *, commit=True):
        user = User()
        session.add(user)
        await session.flush()
        f = FileMetadata(
            user_id=user.id,
            name="d.txt",
            content_type="text/plain",
            head_value="h",
            workspace_id=workspace_id,
        )
        session.add(f)
        await session.flush()
        items = []
        for i, (chunk_id, embedding) in enumerate(chunks):
            session.add(
                ChunkVector(
                    id=chunk_id,
                    file_id=f.id,
                    chunk_index=i,
                    token_count=1,
                    file_content_offset=i * 10,
                    file_content_length=10,
                )
            )
            items.append(
                ChunkEmbedding(
                    chunk_id=chunk_id,
                    workspace_id=workspace_id,
                    file_id=f.id,
                    embedding=embedding,
                )
            )
        await session.flush()
        await repo.add_chunks(session, items)
        if commit:
            await session.commit()
        return f.id

    return _seed
