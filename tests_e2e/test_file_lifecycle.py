import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from crud.vector import PgVectorRepository, SqliteVecRepository, VectorRepository
from db import register_sqlite_vec
from models import Base, FileMetadata, User
from pipelines.embed import EmbeddingPipeline
from pipelines.fs import LocalFileStore
from pipelines.inference import LLMPipeline
from services.file import delete_user_file, link_file_with_project, upload_file
from services.ingestion import index_file_for_project
from services.project import create_user_project, delete_user_project
from services.retrieval import search_project

pytestmark = pytest.mark.e2e


async def _wait_for_embedding_server(base_url: str) -> None:
    deadline = asyncio.get_running_loop().time() + 180
    async with httpx.AsyncClient(timeout=5) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                response = await client.get(f"{base_url.rstrip('/')}/health")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(2)
    raise AssertionError(f"embedding server did not become ready: {base_url}")


@pytest_asyncio.fixture
async def embedding_clients() -> AsyncIterator[tuple[EmbeddingPipeline, LLMPipeline]]:
    base_url = os.getenv("CLYRE_E2E_EMBEDDING_URL", "http://localhost:6761")
    model = os.getenv("CLYRE_E2E_EMBEDDING_MODEL", "Qwen3-Embedding-0.6B")
    await _wait_for_embedding_server(base_url)
    yield EmbeddingPipeline(base_url, model), LLMPipeline(base_url, model)


async def _run_file_lifecycle(
    engine: AsyncEngine,
    repository: VectorRepository,
    root: Path,
    embedder: EmbeddingPipeline,
    tokenizer: LLMPipeline,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await repository.ensure_schema(engine)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    file_store = LocalFileStore(root / "files")
    async with session_maker() as session:
        user = User()
        session.add(user)
        await session.flush()
        project = await create_user_project(session, user_id=user.id, title="E2E project")
        file_metadata = await upload_file(
            session,
            user_id=user.id,
            name="e2e.txt",
            content_type="text/plain",
            data=b"Clyre stores private project knowledge locally.",
            file_store=file_store,
        )
        file_path = root / "files" / user.id / file_metadata.id
        assert file_path.is_file()

        await link_file_with_project(
            session,
            user_id=user.id,
            file_id=file_metadata.id,
            project_id=project.id,
        )
        await index_file_for_project(
            session,
            file_metadata,
            project.id,
            repository=repository,
            embedder=embedder,
            file_store=file_store,
            token_counter=tokenizer.count_tokens_many,
        )

        persisted = await session.get(FileMetadata, file_metadata.id)
        assert persisted.index_status == "ready"
        results = await search_project(
            session,
            "private project knowledge",
            user.id,
            project_ids=[project.id],
            embedder=embedder,
            repository=repository,
        )
        assert len(results) == 1
        assert results[0].chunk_id

        await delete_user_file(
            session,
            user_id=user.id,
            file_id=file_metadata.id,
            repository=repository,
            file_store=file_store,
        )
        assert not file_path.exists()
        assert (
            await repository.search_similar_chunks(
                session,
                await embedder.embed_one("private project knowledge"),
                5,
                [project.id],
            )
            == []
        )
        await delete_user_project(
            session, user_id=user.id, project_id=project.id, repository=repository
        )


async def test_real_sqlite_vec_file_lifecycle(tmp_path, embedding_clients):
    embedder, tokenizer = embedding_clients
    database_path = tmp_path / "e2e.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    register_sqlite_vec(engine)
    try:
        await _run_file_lifecycle(
            engine,
            SqliteVecRepository(),
            tmp_path,
            embedder,
            tokenizer,
        )
    finally:
        await engine.dispose()


async def test_real_pgvector_file_lifecycle(tmp_path, embedding_clients):
    database_url = os.getenv(
        "CLYRE_E2E_DATABASE_URL",
        "postgresql+asyncpg://clyre_e2e:clyre_e2e@localhost:55432/clyre_e2e",
    )
    embedder, tokenizer = embedding_clients
    engine = create_async_engine(database_url)
    try:
        await _run_file_lifecycle(
            engine,
            PgVectorRepository(),
            tmp_path,
            embedder,
            tokenizer,
        )
    finally:
        await engine.dispose()
