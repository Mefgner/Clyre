import httpx
import pytest
from test_file_service import MemoryFileStore

from models import FileMetadata, Project, User
from pipelines.embed import EmbeddingPipeline
from schemas.file import ChunkResult
from services.retrieval import (
    ProjectIndexNotReady,
    fetch_file,
    hydrate_chunks,
    list_project_files,
    search_project,
)


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


async def _user(session) -> User:
    user = User()
    session.add(user)
    await session.flush()
    return user


def _result(chunk_id, file_id, offset=0, length=10, index=0):
    return ChunkResult(
        chunk_id=chunk_id,
        file_id=file_id,
        chunk_index=index,
        file_content_offset=offset,
        file_content_length=length,
        distance=0.1,
    )


async def test_fetch_file_returns_text_for_owner(session):
    user = await _user(session)
    store = MemoryFileStore()
    await store.save(user.id, "f1", "hello world".encode())
    session.add(FileMetadata(id="f1", user_id=user.id, name="a.txt", content_type="text/plain"))
    await session.commit()

    assert await fetch_file(session, "f1", user.id, file_store=store) == "hello world"


async def test_fetch_file_rejects_wrong_user_and_missing_file(session):
    owner = await _user(session)
    other = await _user(session)
    store = MemoryFileStore()
    await store.save(owner.id, "f1", b"secret")
    session.add(
        FileMetadata(id="f1", user_id=owner.id, name="a.txt", content_type="text/plain")
    )
    await session.commit()

    with pytest.raises(ValueError, match="File not found"):
        await fetch_file(session, "f1", other.id, file_store=store)
    with pytest.raises(ValueError, match="File not found"):
        await fetch_file(session, "missing", owner.id, file_store=store)


async def test_list_project_files_lists_only_that_project(session):
    user = await _user(session)
    project = Project(user_id=user.id, title="P")
    other_project = Project(user_id=user.id, title="Q")
    session.add_all([project, other_project])
    await session.flush()
    session.add_all(
        [
            FileMetadata(
                id="fa",
                user_id=user.id,
                name="a.txt",
                content_type="text/plain",
                head_value="aaa",
                project_id=project.id,
                index_status="ready",
            ),
            FileMetadata(
                id="fb",
                user_id=user.id,
                name="b.txt",
                content_type="text/csv",
                head_value=None,
                project_id=other_project.id,
                index_status="not_indexed",
            ),
            FileMetadata(
                id="fc",
                user_id=user.id,
                name="c.txt",
                content_type="text/plain",
                head_value="ccc",
                project_id=None,
                index_status="not_indexed",
            ),
        ]
    )
    await session.commit()

    metas = await list_project_files(session, project.id, user.id)

    assert [(m.id, m.name) for m in metas] == [("fa", "a.txt")]
    assert metas[0].content_type == "text/plain"
    assert metas[0].head_value == "aaa"
    assert metas[0].index_status == "ready"


async def test_list_project_files_yields_empty_for_foreign_project(session):
    owner = await _user(session)
    other = await _user(session)
    project = Project(user_id=owner.id, title="P")
    session.add(project)
    await session.flush()
    session.add(
        FileMetadata(
            id="fa",
            user_id=owner.id,
            name="a.txt",
            content_type="text/plain",
            project_id=project.id,
            index_status="ready",
        )
    )
    await session.commit()

    assert await list_project_files(session, project.id, other.id) == []


async def test_hydrate_chunks_slices_across_files_preserving_order(session):
    user = await _user(session)
    store = MemoryFileStore()
    await store.save(user.id, "f1", b"0123456789ABCDEF")
    await store.save(user.id, "f2", b"wxyz")
    session.add_all(
        [
            FileMetadata(id="f1", user_id=user.id, name="1.txt", content_type="text/plain"),
            FileMetadata(id="f2", user_id=user.id, name="2.txt", content_type="text/plain"),
        ]
    )
    await session.commit()

    results = [
        _result("k3", "f2", offset=1, length=2),
        _result("k1", "f1", offset=10, length=6),
        _result("k2", "f1", offset=0, length=4),
    ]

    chunks = await hydrate_chunks(session, results, user.id, file_store=store)

    assert [c.chunk_id for c in chunks] == ["k3", "k1", "k2"]
    assert [c.text for c in chunks] == ["xy", "ABCDEF", "0123"]
    assert [c.file_id for c in chunks] == ["f2", "f1", "f1"]
    assert [c.chunk_index for c in chunks] == [0, 0, 0]


async def test_hydrate_chunks_enforces_ownership(session):
    owner = await _user(session)
    other = await _user(session)
    store = MemoryFileStore()
    await store.save(other.id, "fx", b"private text here")
    session.add(
        FileMetadata(id="fx", user_id=other.id, name="x.txt", content_type="text/plain")
    )
    await session.commit()

    with pytest.raises(ValueError, match="File not found"):
        await hydrate_chunks(
            session, [_result("k1", "fx", length=5)], owner.id, file_store=store
        )
