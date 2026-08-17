from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from crud.file import get_project_index_statuses
from crud.project import get_project_ids_for_user
from crud.vector import VectorRepository, get_vector_repository
from pipelines.embed import EmbeddingPipeline, get_embedding_pipeline
from schemas.file import ChunkResult
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


__all__ = [
    "DEFAULT_TOP_K",
    "ProjectIndexNotReady",
    "ProjectIndexUnavailable",
    "project_scopes",
    "search_project",
]
