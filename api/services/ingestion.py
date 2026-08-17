from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from crud.file import get_project_link
from crud.project import get_project_for_user
from crud.vector import VectorRepository, get_vector_repository
from models import ChunkVector, FileMetadata
from pipelines.embed import get_embedding_pipeline
from pipelines.fs import get_file_store
from pipelines.ingest import chunk_text, extract_text
from pipelines.llama import get_current_llama_pipeline
from schemas.file import ChunkEmbedding
from services.embedding_space import ensure_for_write
from utils import env

TokenCounter = Callable[[list[str]], Awaitable[list[int]]]


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class ReadableFileStore(Protocol):
    async def read(self, user_id: str, file_id: str) -> bytes: ...


async def _purge_file_vectors(
    session: AsyncSession, file_id: str, repository: VectorRepository
) -> None:
    # The vector store is outside the ORM and therefore cannot be reached by the
    # relationship cascade. Both sides must be cleared before re-indexing.
    await repository.delete_by_file(session, file_id)
    await session.execute(delete(ChunkVector).where(ChunkVector.file_id == file_id))


async def purge_file_vectors(
    session: AsyncSession,
    file_id: str,
    *,
    repository: VectorRepository | None = None,
) -> None:
    """Remove all searchable data for a file and commit the deletion."""
    repository = repository or get_vector_repository()
    try:
        await _purge_file_vectors(session, file_id, repository)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def ingest_file(
    session: AsyncSession,
    file: FileMetadata,
    *,
    embedder: Embedder | None = None,
    repository: VectorRepository | None = None,
    file_store: ReadableFileStore | None = None,
    token_counter: TokenCounter | None = None,
) -> list[ChunkVector]:
    """Extract, chunk and index one project file.

    Re-ingestion is intentionally a full replacement. All writes share the
    caller's transaction, so an embedding or tokenization failure rolls back
    both the old and new index data.
    """
    if not file.project_id:
        raise ValueError("file must be linked to a project before ingestion")

    embedder = embedder or get_embedding_pipeline()
    repository = repository or get_vector_repository()
    file_store = file_store or get_file_store()
    token_counter = token_counter or get_current_llama_pipeline().count_tokens_many

    try:
        file.index_status = "pending"
        file.index_error = None
        file.indexed_at = None
        session.add(file)
        await session.commit()

        await ensure_for_write(session)
        raw_data = await file_store.read(file.user_id, file.id)
        text = extract_text(raw_data, content_type=file.content_type, filename=file.name)
        chunks = chunk_text(text, chunk_size=env.CHUNK_SIZE, overlap=env.CHUNK_OVERLAP)

        await _purge_file_vectors(session, file.id, repository)
        if not chunks:
            await session.commit()
            return []

        embeddings = await embedder.embed([chunk.text for chunk in chunks])
        if len(embeddings) != len(chunks):
            raise ValueError(
                f"embedding service returned {len(embeddings)} vectors for {len(chunks)} chunks"
            )
        token_counts = await token_counter([chunk.text for chunk in chunks])
        if len(token_counts) != len(chunks):
            raise ValueError(
                f"tokenizer returned {len(token_counts)} counts for {len(chunks)} chunks"
            )

        rows = [
            ChunkVector(
                file_id=file.id,
                chunk_index=chunk.index,
                token_count=token_count,
                file_content_offset=chunk.offset,
                file_content_length=chunk.length,
            )
            for chunk, token_count in zip(chunks, token_counts)
        ]
        session.add_all(rows)
        await session.flush()
        await repository.add_chunks(
            session,
            [
                ChunkEmbedding(
                    chunk_id=row.id,
                    project_id=file.project_id,
                    file_id=file.id,
                    embedding=embedding,
                )
                for row, embedding in zip(rows, embeddings)
            ],
        )
        file.index_status = "ready"
        file.index_error = None
        file.indexed_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(file)
        await session.commit()
        return rows
    except Exception:
        await session.rollback()
        raise


async def index_file_for_project(
    session: AsyncSession,
    file: FileMetadata,
    project_id: str,
    **kwargs,
) -> list[ChunkVector]:
    """Index a file for its owner's project after it has been linked."""
    project = await get_project_for_user(session, project_id, file.user_id)
    if not project:
        raise ValueError("Project not found")
    if not await get_project_link(session, file.id, project_id):
        raise ValueError("File must be linked to the project before indexing")

    file.project_id = project.id
    session.add(file)
    return await ingest_file(session, file, **kwargs)


__all__ = ["index_file_for_project", "ingest_file", "purge_file_vectors"]
