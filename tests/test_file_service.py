from dataclasses import dataclass, field

import pytest
from sqlalchemy import select

from models import FileHasProject, FileHasThread, Project, Thread, User
from services.file import (
    delete_user_file,
    get_files,
    get_user_file,
    link_file_with_project,
    link_file_with_thread,
    unlink_file_with_project,
    upload_file,
)
from services.ingestion import index_file_for_project


@dataclass
class MemoryFileStore:
    files: dict[tuple[str, str], bytes] = field(default_factory=dict)

    async def save(self, user_id: str, file_id: str, data: bytes) -> None:
        self.files[(user_id, file_id)] = data

    async def read(self, user_id: str, file_id: str) -> bytes:
        return self.files[(user_id, file_id)]

    async def delete(self, user_id: str, file_id: str) -> None:
        self.files.pop((user_id, file_id), None)


async def _user(session) -> User:
    user = User()
    session.add(user)
    await session.flush()
    return user


class FixedEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 7 for _ in texts]


async def _tokens(texts: list[str]) -> list[int]:
    return [len(text.split()) for text in texts]


async def test_upload_lists_file_and_keeps_it_out_of_project(session):
    user = await _user(session)
    store = MemoryFileStore()

    file_metadata = await upload_file(
        session,
        user_id=user.id,
        name="notes.txt",
        content_type="text/plain",
        data=b"hello project",
        file_store=store,
    )

    assert store.files[(user.id, file_metadata.id)] == b"hello project"
    assert file_metadata.head_value == "hello project"
    assert file_metadata.project_id is None
    assert await get_files(session, user.id) == [file_metadata]


async def test_file_isolation_and_delete_remove_blob_and_row(session, repo):
    owner = await _user(session)
    other = await _user(session)
    store = MemoryFileStore()
    file_metadata = await upload_file(
        session,
        user_id=owner.id,
        name="private.txt",
        content_type="text/plain",
        data=b"private",
        file_store=store,
    )

    with pytest.raises(ValueError, match="File not found"):
        await get_user_file(session, other.id, file_metadata.id)

    await delete_user_file(
        session,
        user_id=owner.id,
        file_id=file_metadata.id,
        repository=repo,
        file_store=store,
    )

    assert (owner.id, file_metadata.id) not in store.files
    with pytest.raises(ValueError, match="File not found"):
        await get_user_file(session, owner.id, file_metadata.id)


async def test_file_can_be_linked_to_owned_thread_and_project(session):
    user = await _user(session)
    project = Project(user_id=user.id, title="Project")
    thread = Thread(user_id=user.id, title="Thread")
    session.add_all([project, thread])
    await session.flush()
    file_metadata = await upload_file(
        session,
        user_id=user.id,
        name="context.txt",
        content_type="text/plain",
        data=b"context",
        file_store=MemoryFileStore(),
    )

    await link_file_with_thread(
        session, user_id=user.id, file_id=file_metadata.id, thread_id=thread.id
    )
    await link_file_with_project(
        session, user_id=user.id, file_id=file_metadata.id, project_id=project.id
    )
    await link_file_with_project(
        session, user_id=user.id, file_id=file_metadata.id, project_id=project.id
    )

    thread_links = await session.execute(
        select(FileHasThread).where(FileHasThread.file_id == file_metadata.id)
    )
    project_links = await session.execute(
        select(FileHasProject).where(FileHasProject.file_id == file_metadata.id)
    )
    assert len(thread_links.scalars().all()) == 1
    assert len(project_links.scalars().all()) == 1
    assert file_metadata.project_id == project.id
    assert file_metadata.index_status == "pending"


async def test_unlink_project_purges_vectors(session, repo):
    user = await _user(session)
    project = Project(user_id=user.id, title="Project")
    session.add(project)
    await session.flush()
    store = MemoryFileStore()
    file_metadata = await upload_file(
        session,
        user_id=user.id,
        name="indexed.txt",
        content_type="text/plain",
        data=b"indexed project content",
        file_store=store,
    )
    await link_file_with_project(
        session, user_id=user.id, file_id=file_metadata.id, project_id=project.id
    )
    await index_file_for_project(
        session,
        file_metadata,
        project.id,
        repository=repo,
        embedder=FixedEmbedder(),
        file_store=store,
        token_counter=_tokens,
    )
    assert await repo.search_similar_chunks(session, [1.0] + [0.0] * 7, 5, [project.id])

    await unlink_file_with_project(
        session,
        user_id=user.id,
        file_id=file_metadata.id,
        project_id=project.id,
        repository=repo,
    )

    assert await repo.search_similar_chunks(session, [1.0] + [0.0] * 7, 5, [project.id]) == []
    assert file_metadata.project_id is None
    assert file_metadata.index_status == "not_indexed"
