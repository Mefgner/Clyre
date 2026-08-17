from dataclasses import dataclass

from models import FileMetadata, User
from services.file import link_file_with_project, upload_file
from services.ingestion import index_file_for_project
from services.project import (
    create_user_project,
    delete_user_project,
    get_projects,
    update_user_project,
)


@dataclass
class MemoryFileStore:
    data: bytes

    async def save(self, user_id: str, file_id: str, data: bytes) -> None:
        self.data = data

    async def read(self, user_id: str, file_id: str) -> bytes:
        return self.data

    async def delete(self, user_id: str, file_id: str) -> None:
        return None


class FixedEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 7 for _ in texts]


async def _tokens(texts: list[str]) -> list[int]:
    return [len(text.split()) for text in texts]


async def test_project_crud_and_delete_purges_index(session, repo):
    user = User()
    session.add(user)
    await session.flush()
    project = await create_user_project(session, user_id=user.id, title="  First project ")

    assert [item.title for item in await get_projects(session, user.id)] == ["First project"]
    project = await update_user_project(
        session, user_id=user.id, project_id=project.id, title="Renamed"
    )
    assert project.title == "Renamed"

    store = MemoryFileStore(b"project content")
    file_metadata = await upload_file(
        session,
        user_id=user.id,
        name="project.txt",
        content_type="text/plain",
        data=store.data,
        file_store=store,
    )
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
        repository=repo,
        embedder=FixedEmbedder(),
        file_store=store,
        token_counter=_tokens,
    )

    assert await repo.search_similar_chunks(session, [1.0] + [0.0] * 7, 5, [project.id])

    await delete_user_project(session, user_id=user.id, project_id=project.id, repository=repo)

    assert await repo.search_similar_chunks(session, [1.0] + [0.0] * 7, 5, [project.id]) == []
    persisted_file = await session.get(FileMetadata, file_metadata.id)
    assert persisted_file.project_id is None
    assert persisted_file.index_status == "not_indexed"
    assert await get_projects(session, user.id) == []
