from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.vector import VectorIndexMeta
from utils import env


class EmbeddingSpaceMismatch(RuntimeError):
    pass


def _current() -> tuple[str, int, bool]:
    return (env.EMBEDDING_MODEL, env.VECTOR_DIM, env.NORMALIZE_VECTORS)


async def _get(session: AsyncSession) -> VectorIndexMeta | None:
    result = await session.execute(select(VectorIndexMeta).limit(1))
    return result.scalar_one_or_none()


def _check(meta: VectorIndexMeta, model: str, dim: int, normalized: bool) -> None:
    if (meta.embedding_model, meta.embedding_dim, meta.normalized) != (model, dim, normalized):
        raise EmbeddingSpaceMismatch(
            f"vector index built with {meta.embedding_model}/dim={meta.embedding_dim}/"
            f"norm={meta.normalized}, config is {model}/dim={dim}/norm={normalized}; "
            "re-embed the project index to change the embedding model"
        )


async def ensure_for_write(session: AsyncSession) -> None:
    model, dim, normalized = _current()
    meta = await _get(session)
    if meta is None:
        session.add(
            VectorIndexMeta(embedding_model=model, embedding_dim=dim, normalized=normalized)
        )
        await session.flush()
        return
    _check(meta, model, dim, normalized)


async def validate_for_read(session: AsyncSession) -> None:
    meta = await _get(session)
    if meta is None:
        return
    _check(meta, *_current())


__all__ = ["EmbeddingSpaceMismatch", "ensure_for_write", "validate_for_read"]
