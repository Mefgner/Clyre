from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from crud.file import (
    get_file_for_user,
    get_owned_file_ids,
    get_project_index_statuses,
)
from crud.file import list_project_files as list_project_file_rows
from crud.project import get_project_ids_for_user
from crud.vector import VectorRepository, get_vector_repository
from pipelines.embed import EmbeddingPipeline, get_embedding_pipeline
from pipelines.fs import FileStore, get_file_store
from schemas.file import ChunkResult, ChunkText, FileMeta
from services.embedding_space import validate_for_read

DEFAULT_TOP_K = 5


class ProjectIndexNotReady(RuntimeError):
    pass


class ProjectIndexUnavailable(RuntimeError):
    pass


async def search_project(
    session: AsyncSession,
    query: str,
    user_id: str,
    k: int = DEFAULT_TOP_K,
    *,
    project_ids: Sequence[str] | None = None,
    embedder: EmbeddingPipeline | None = None,
    repository: VectorRepository | None = None,
) -> list[ChunkResult]:
    embedder = embedder or get_embedding_pipeline()
    repository = repository or get_vector_repository()
    scopes = await project_scopes(session, user_id, project_ids=project_ids)
    if not scopes:
        return []
    statuses = await get_project_index_statuses(session, scopes)
    all_statuses = set().union(*statuses.values()) if statuses else set()
    if "failed" in all_statuses:
        raise ProjectIndexUnavailable("one or more project indexes have failed files")
    if all_statuses - {"ready"}:
        raise ProjectIndexNotReady("one or more project indexes are not ready")
    await validate_for_read(session)
    embedding = await embedder.embed_one(query)
    return await repository.search_similar_chunks(session, embedding, k, scopes)


async def project_scopes(
    session: AsyncSession, user_id: str, project_ids: Sequence[str] | None = None
) -> list[str]:
    """Return only project IDs owned by the user for a retrieval scope."""
    return await get_project_ids_for_user(session, user_id, project_ids)


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


async def fetch_file(
    session: AsyncSession,
    file_id: str,
    user_id: str,
    *,
    file_store: FileStore | None = None,
) -> str:
    file_metadata = await get_file_for_user(session, file_id, user_id)
    if not file_metadata:
        raise ValueError("File not found")
    file_store = file_store or get_file_store()
    data = await file_store.read(user_id, file_metadata.id)
    return _decode(data)


async def list_project_files(
    session: AsyncSession, project_id: str, user_id: str
) -> list[FileMeta]:
    """List files indexed under an owned project; foreign projects yield an empty list."""
    scopes = await project_scopes(session, user_id, [project_id])
    if not scopes:
        return []
    files = await list_project_file_rows(session, scopes[0])
    return [
        FileMeta(
            id=f.id,
            name=f.name,
            content_type=f.content_type,
            head_value=f.head_value,
            index_status=f.index_status,
        )
        for f in files
    ]


async def hydrate_chunks(
    session: AsyncSession,
    results: Sequence[ChunkResult],
    user_id: str,
    *,
    file_store: FileStore | None = None,
) -> list[ChunkText]:
    """Load chunk texts for search results, reading each referenced file at most once."""
    if not results:
        return []
    owned_ids = await get_owned_file_ids(session, list({r.file_id for r in results}), user_id)
    missing = {r.file_id for r in results} - owned_ids
    if missing:
        raise ValueError("File not found")
    file_store = file_store or get_file_store()
    texts: dict[str, str] = {}
    for file_id in owned_ids:
        data = await file_store.read(user_id, file_id)
        texts[file_id] = _decode(data)
    return [
        ChunkText(
            chunk_id=r.chunk_id,
            file_id=r.file_id,
            chunk_index=r.chunk_index,
            text=texts[r.file_id][
                r.file_content_offset : r.file_content_offset + r.file_content_length
            ],
        )
        for r in results
    ]


__all__ = [
    "DEFAULT_TOP_K",
    "ProjectIndexNotReady",
    "ProjectIndexUnavailable",
    "fetch_file",
    "hydrate_chunks",
    "list_project_files",
    "project_scopes",
    "search_project",
]
