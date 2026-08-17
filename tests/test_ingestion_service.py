from dataclasses import dataclass

import pytest

from models import FileMetadata, Project, User
from services.file import link_file_with_project
from services.ingestion import index_file_for_project, ingest_file, purge_file_vectors


@dataclass
class MemoryFileStore:
    data: bytes

    async def read(self, user_id: str, file_id: str) -> bytes:
        return self.data


@dataclass
class FixedEmbedder:
    dimension: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [float(index + 1)] + [0.0] * (self.dimension - 1) for index, _ in enumerate(texts)
        ]


class FailingEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding server unavailable")


async def _file(
    session,
    *,
    content: str,
    project_id: str | None = "project-1",
    user_id: str | None = None,
) -> tuple[FileMetadata, MemoryFileStore]:
    if user_id is None:
        user = User()
        session.add(user)
        await session.flush()
        user_id = user.id
    result = FileMetadata(
        user_id=user_id,
        name="notes.txt",
        content_type="text/plain",
        project_id=project_id,
    )
    session.add(result)
    await session.flush()
    return result, MemoryFileStore(content.encode())


async def test_ingest_file_writes_chunks_and_vectors(session, repo, monkeypatch):
    from utils import env

    monkeypatch.setattr(env, "CHUNK_SIZE", 10)
    monkeypatch.setattr(env, "CHUNK_OVERLAP", 2)
    file, store = await _file(session, content="one two three four five")

    rows = await ingest_file(
        session,
        file,
        repository=repo,
        embedder=FixedEmbedder(8),
        file_store=store,
        token_counter=_counts,
    )

    assert len(rows) > 1
    assert all(row.token_count > 0 for row in rows)
    assert file.index_status == "ready"

    results = await repo.search_similar_chunks(session, [1.0] + [0.0] * 7, 5, ["project-1"])
    assert len(results) == len(rows)


async def _counts(texts: list[str]) -> list[int]:
    return [len(text.split()) for text in texts]


async def test_reingest_replaces_old_vectors(session, repo):
    file, _ = await _file(session, content="old content")
    await ingest_file(
        session,
        file,
        repository=repo,
        embedder=FixedEmbedder(8),
        file_store=MemoryFileStore(b"new content"),
        token_counter=_counts,
    )
    rows = await ingest_file(
        session,
        file,
        repository=repo,
        embedder=FixedEmbedder(8),
        file_store=MemoryFileStore(b"replacement content"),
        token_counter=_counts,
    )

    assert len(rows) == 1
    results = await repo.search_similar_chunks(session, [1.0] + [0.0] * 7, 5, ["project-1"])
    assert len(results) == 1
    assert results[0].file_content_length == len("replacement content")


async def test_failed_reingest_restores_old_vectors(session, repo):
    file, store = await _file(session, content="old content")
    file_id = file.id
    await ingest_file(
        session,
        file,
        repository=repo,
        embedder=FixedEmbedder(8),
        file_store=store,
        token_counter=_counts,
    )

    with pytest.raises(RuntimeError, match="embedding server unavailable"):
        await ingest_file(
            session,
            file,
            repository=repo,
            embedder=FailingEmbedder(),
            file_store=MemoryFileStore(b"replacement content"),
            token_counter=_counts,
        )

    persisted_file = await session.get(FileMetadata, file_id)
    assert persisted_file.index_status == "pending"
    results = await repo.search_similar_chunks(session, [1.0] + [0.0] * 7, 5, ["project-1"])
    assert len(results) == 1
    assert results[0].file_content_length == len("old content")


async def test_promotion_requires_and_uses_owned_project(session, repo):
    user = User()
    session.add(user)
    await session.flush()
    project = Project(user_id=user.id, title="Knowledge")
    session.add(project)
    await session.flush()
    file, store = await _file(
        session, content="project knowledge", project_id=None, user_id=user.id
    )
    await link_file_with_project(
        session, user_id=user.id, file_id=file.id, project_id=project.id
    )

    await index_file_for_project(
        session,
        file,
        project.id,
        repository=repo,
        embedder=FixedEmbedder(8),
        file_store=store,
        token_counter=_counts,
    )

    assert file.project_id == project.id
    assert file.index_status == "ready"
    results = await repo.search_similar_chunks(session, [1.0] + [0.0] * 7, 5, [project.id])
    assert len(results) == 1


async def test_purge_file_vectors_removes_metadata_and_vectors(session, repo):
    file, store = await _file(session, content="to delete")
    await ingest_file(
        session,
        file,
        repository=repo,
        embedder=FixedEmbedder(8),
        file_store=store,
        token_counter=_counts,
    )

    await purge_file_vectors(session, file.id, repository=repo)

    assert await repo.search_similar_chunks(session, [1.0] + [0.0] * 7, 5, ["project-1"]) == []
