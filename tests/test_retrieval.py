import httpx
import pytest

from models import FileMetadata, Project, User
from pipelines.embed import EmbeddingPipeline
from services.retrieval import ProjectIndexNotReady, search_project


def _embedder_returning(vector: list[float]) -> EmbeddingPipeline:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": vector}]})

    return EmbeddingPipeline("http://emb", "m", transport=httpx.MockTransport(handler))


async def test_search_project_embeds_query_and_ranks(session, repo, seeder):
    user = User()
    session.add(user)
    await session.flush()
    project = Project(user_id=user.id, title="Project")
    session.add(project)
    await session.flush()
    await seeder(
        project.id,
        [
            ("k1", [1.0, 0, 0, 0, 0, 0, 0, 0]),
            ("k2", [0.9, 0.1, 0, 0, 0, 0, 0, 0]),
            ("k3", [0.0, 1.0, 0, 0, 0, 0, 0, 0]),
        ],
    )

    embedder = _embedder_returning([1.0, 0, 0, 0, 0, 0, 0, 0])
    res = await search_project(
        session, "query about k1", user.id, k=2, embedder=embedder, repository=repo
    )

    assert [r.chunk_id for r in res] == ["k1", "k2"]
    assert res[0].file_id  # joined metadata present


async def test_search_project_respects_project(session, repo, seeder):
    owner = User()
    other = User()
    session.add_all([owner, other])
    await session.flush()
    owned_project = Project(user_id=owner.id, title="Owned")
    other_project = Project(user_id=other.id, title="Other")
    session.add_all([owned_project, other_project])
    await session.flush()
    await seeder(owned_project.id, [("a1", [1.0, 0, 0, 0, 0, 0, 0, 0])])
    embedder = _embedder_returning([1.0, 0, 0, 0, 0, 0, 0, 0])

    res = await search_project(
        session,
        "q",
        owner.id,
        project_ids=[other_project.id],
        k=5,
        embedder=embedder,
        repository=repo,
    )
    assert res == []


async def test_search_project_waits_for_index(session, repo, seeder):
    user = User()
    session.add(user)
    await session.flush()
    project = Project(user_id=user.id, title="Pending")
    session.add(project)
    await session.flush()
    file_id = await seeder(project.id, [("pending-1", [1.0] + [0.0] * 7)])
    file_metadata = await session.get(FileMetadata, file_id)
    file_metadata.index_status = "pending"
    await session.commit()

    with pytest.raises(ProjectIndexNotReady):
        await search_project(
            session,
            "q",
            user.id,
            embedder=_embedder_returning([1.0] + [0.0] * 7),
            repository=repo,
        )
