from sqlalchemy.ext.asyncio import AsyncSession

from crud.vector import VectorRepository, get_vector_repository
from pipelines.embed import EmbeddingPipeline, get_embedding_pipeline
from schemas.file import ChunkResult

DEFAULT_TOP_K = 5


async def search_workspace(
    session: AsyncSession,
    query: str,
    workspace_id: str,
    k: int = DEFAULT_TOP_K,
    *,
    embedder: EmbeddingPipeline | None = None,
    repository: VectorRepository | None = None,
) -> list[ChunkResult]:
    embedder = embedder or get_embedding_pipeline()
    repository = repository or get_vector_repository()
    embedding = await embedder.embed_one(query)
    return await repository.search_similar_chunks(session, embedding, k, workspace_id)


__all__ = ["search_workspace", "DEFAULT_TOP_K"]
