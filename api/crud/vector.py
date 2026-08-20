from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import Column, MetaData, String, Table, delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from models import ChunkVector
from schemas.file import ChunkEmbedding, ChunkResult
from utils import env

_VEC_TABLE = "vec_chunk"
_CHUNK_TABLE = ChunkVector.__tablename__


class VectorRepository(Protocol):
    """Owns the embedding store, which lives outside the ORM because pgvector
    (a column type) and sqlite-vec (a virtual table) are structurally different.
    Selected by DB_ENGINE; nothing else knows which backend is in use."""

    async def ensure_schema(self, engine: AsyncEngine) -> None: ...

    async def add_chunks(self, session: AsyncSession, items: list[ChunkEmbedding]) -> None: ...

    async def delete_by_file(self, session: AsyncSession, file_id: str) -> None: ...

    async def search_similar_chunks(
        self,
        session: AsyncSession,
        embedding: list[float],
        k: int,
        project_ids: Sequence[str],
    ) -> list[ChunkResult]: ...


class SqliteVecRepository:
    async def ensure_schema(self, engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS {_VEC_TABLE} USING vec0("
                    "chunk_id TEXT PRIMARY KEY, "
                    "project_id TEXT, "
                    "file_id TEXT, "
                    f"embedding float[{env.VECTOR_DIM}] distance_metric=cosine)"
                )
            )

    async def add_chunks(self, session: AsyncSession, items: list[ChunkEmbedding]) -> None:
        if not items:
            return
        import sqlite_vec

        await session.execute(
            text(
                f"INSERT INTO {_VEC_TABLE}(chunk_id, project_id, file_id, embedding) "
                "VALUES (:chunk_id, :project_id, :file_id, :embedding)"
            ),
            [
                {
                    "chunk_id": it.chunk_id,
                    "project_id": it.project_id,
                    "file_id": it.file_id,
                    "embedding": sqlite_vec.serialize_float32(it.embedding),
                }
                for it in items
            ],
        )

    async def delete_by_file(self, session: AsyncSession, file_id: str) -> None:
        await session.execute(
            text(f"DELETE FROM {_VEC_TABLE} WHERE file_id = :file_id"),
            {"file_id": file_id},
        )

    async def search_similar_chunks(
        self,
        session: AsyncSession,
        embedding: list[float],
        k: int,
        project_ids: Sequence[str],
    ) -> list[ChunkResult]:
        import sqlite_vec

        if not project_ids or k <= 0:
            return []
        query = sqlite_vec.serialize_float32(embedding)
        results: list[ChunkResult] = []
        for project_id in dict.fromkeys(project_ids):
            rows = await session.execute(
                text(
                    "SELECT cv.id AS chunk_id, cv.file_id AS file_id, "
                    "cv.chunk_index AS chunk_index, "
                    "cv.file_content_offset AS file_content_offset, "
                    "cv.file_content_length AS file_content_length, "
                    "v.distance AS distance "
                    f"FROM {_VEC_TABLE} v JOIN {_CHUNK_TABLE} cv ON cv.id = v.chunk_id "
                    "WHERE v.project_id = :project_id AND v.embedding MATCH :query AND k = :k "
                    "ORDER BY v.distance"
                ),
                {"project_id": project_id, "query": query, "k": k},
            )
            results.extend(ChunkResult(**row._mapping) for row in rows)
        return sorted(results, key=lambda item: item.distance)[:k]


class PgVectorRepository:
    def __init__(self) -> None:
        from pgvector.sqlalchemy import Vector

        self._metadata = MetaData()
        self._table = Table(
            "chunk_embedding",
            self._metadata,
            Column("chunk_id", String(36), primary_key=True),
            Column("project_id", String(36), nullable=False, index=True),
            Column("file_id", String(36), nullable=False, index=True),
            Column("embedding", Vector(env.VECTOR_DIM), nullable=False),
        )

    async def ensure_schema(self, engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(self._metadata.create_all)
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS chunk_embedding_hnsw "
                    "ON chunk_embedding USING hnsw (embedding vector_cosine_ops)"
                )
            )

    async def add_chunks(self, session: AsyncSession, items: list[ChunkEmbedding]) -> None:
        if not items:
            return
        await session.execute(
            insert(self._table),
            [
                {
                    "chunk_id": it.chunk_id,
                    "project_id": it.project_id,
                    "file_id": it.file_id,
                    "embedding": it.embedding,
                }
                for it in items
            ],
        )

    async def delete_by_file(self, session: AsyncSession, file_id: str) -> None:
        await session.execute(delete(self._table).where(self._table.c.file_id == file_id))

    async def search_similar_chunks(
        self,
        session: AsyncSession,
        embedding: list[float],
        k: int,
        project_ids: Sequence[str],
    ) -> list[ChunkResult]:
        if not project_ids or k <= 0:
            return []
        distance = self._table.c.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(
                self._table.c.chunk_id.label("chunk_id"),
                ChunkVector.file_id.label("file_id"),
                ChunkVector.chunk_index.label("chunk_index"),
                ChunkVector.file_content_offset.label("file_content_offset"),
                ChunkVector.file_content_length.label("file_content_length"),
                distance,
            )
            .join(ChunkVector, ChunkVector.id == self._table.c.chunk_id)
            .where(self._table.c.project_id.in_(project_ids))
            .order_by(distance)
            .limit(k)
        )
        rows = await session.execute(stmt)
        return [ChunkResult(**row._mapping) for row in rows]


_repository: VectorRepository | None = None


def get_vector_repository() -> VectorRepository:
    global _repository
    if _repository is None:
        # Pick the backend from the live engine dialect, not the DB_ENGINE env:
        # the Docker/Postgres path must not instantiate the sqlite repository.
        from db import get_session_manager

        engine = get_session_manager().async_engine
        _repository = (
            SqliteVecRepository() if engine.dialect.name == "sqlite" else PgVectorRepository()
        )
    return _repository


__all__ = [
    "VectorRepository",
    "SqliteVecRepository",
    "PgVectorRepository",
    "get_vector_repository",
]
