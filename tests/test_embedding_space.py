import pytest

from services.embedding_space import (
    EmbeddingSpaceMismatch,
    ensure_for_write,
    validate_for_read,
)
from utils import env


async def test_validate_read_on_empty_index_is_noop(session):
    await validate_for_read(session)  # no meta row yet → no error


async def test_ensure_write_initializes_then_validates(session):
    await ensure_for_write(session)
    await ensure_for_write(session)  # same config → fine
    await validate_for_read(session)


async def test_mismatch_raises_on_read(session, monkeypatch):
    await ensure_for_write(session)
    monkeypatch.setattr(env, "EMBEDDING_MODEL", "some-other-model")
    with pytest.raises(EmbeddingSpaceMismatch):
        await validate_for_read(session)


async def test_mismatch_raises_on_second_write(session, monkeypatch):
    await ensure_for_write(session)
    monkeypatch.setattr(env, "VECTOR_DIM", env.VECTOR_DIM + 1)
    with pytest.raises(EmbeddingSpaceMismatch):
        await ensure_for_write(session)
