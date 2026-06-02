import pytest

DIM = 8


def vec(*components: float) -> list[float]:
    v = list(components) + [0.0] * DIM
    return v[:DIM]


# --- SQLite repository (real, end-to-end) -----------------------------------


async def test_factory_selects_sqlite_by_engine():
    from crud.vector import SqliteVecRepository, get_vector_repository

    assert isinstance(get_vector_repository(), SqliteVecRepository)


async def test_ensure_schema_is_idempotent(engine, repo):
    await repo.ensure_schema(engine)
    await repo.ensure_schema(engine)


async def test_add_empty_is_noop(session, repo):
    await repo.add_chunks(session, [])
    res = await repo.search_similar_chunks(session, vec(1.0), k=5, workspace_id="ws")
    assert res == []


async def test_search_empty_store(session, repo):
    res = await repo.search_similar_chunks(session, vec(1.0), k=5, workspace_id="ws")
    assert res == []


async def test_ranking_and_joined_metadata(session, repo, seeder):
    await seeder("ws", [("k1", vec(1.0)), ("k2", vec(0.9, 0.1)), ("k3", vec(0.0, 1.0))])

    res = await repo.search_similar_chunks(session, vec(1.0), k=2, workspace_id="ws")

    assert [r.chunk_id for r in res] == ["k1", "k2"]
    top = res[0]
    assert top.chunk_index == 0
    assert top.file_content_offset == 0
    assert top.file_content_length == 10
    assert top.file_id  # populated via JOIN to chunk_vector
    assert top.distance == pytest.approx(0.0, abs=1e-5)
    assert res[1].distance > top.distance


async def test_k_limits_results(session, repo, seeder):
    await seeder("ws", [("k1", vec(1.0)), ("k2", vec(0.9, 0.1)), ("k3", vec(0.8, 0.2))])

    res = await repo.search_similar_chunks(session, vec(1.0), k=1, workspace_id="ws")

    assert len(res) == 1
    assert res[0].chunk_id == "k1"


async def test_workspace_isolation(session, repo, seeder):
    await seeder("ws-a", [("a1", vec(1.0))])
    await seeder("ws-b", [("b1", vec(1.0))])

    res_a = await repo.search_similar_chunks(session, vec(1.0), k=5, workspace_id="ws-a")
    assert [r.chunk_id for r in res_a] == ["a1"]

    res_missing = await repo.search_similar_chunks(session, vec(1.0), k=5, workspace_id="ws-x")
    assert res_missing == []


async def test_delete_by_file(session, repo, seeder):
    file_id = await seeder("ws", [("k1", vec(1.0)), ("k2", vec(0.9, 0.1))])

    await repo.delete_by_file(session, file_id)
    await session.commit()

    res = await repo.search_similar_chunks(session, vec(1.0), k=5, workspace_id="ws")
    assert res == []


async def test_delete_by_file_leaves_other_files(session, repo, seeder):
    file_a = await seeder("ws", [("a1", vec(1.0))])
    await seeder("ws", [("b1", vec(1.0))])

    await repo.delete_by_file(session, file_a)
    await session.commit()

    res = await repo.search_similar_chunks(session, vec(1.0), k=5, workspace_id="ws")
    assert [r.chunk_id for r in res] == ["b1"]


# --- Postgres repository (compile-only; no live server) ----------------------


def test_pg_repository_sql_compiles():
    from sqlalchemy import delete, insert, select
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from crud.vector import PgVectorRepository
    from models import ChunkVector

    repo = PgVectorRepository()
    pg = postgresql.dialect()

    ddl = str(CreateTable(repo._table).compile(dialect=pg))
    assert "VECTOR(8)" in ddl  # VECTOR_DIM=8 under test

    t = repo._table
    distance = t.c.embedding.cosine_distance([0.0] * DIM).label("distance")
    stmt = (
        select(t.c.chunk_id, distance)
        .join(ChunkVector, ChunkVector.id == t.c.chunk_id)
        .where(t.c.workspace_id == "ws")
        .order_by(distance)
        .limit(3)
    )
    sql = str(stmt.compile(dialect=pg))
    assert "<=>" in sql
    assert "JOIN chunk_vector" in sql

    # insert / delete construct valid SQL
    str(insert(t).compile(dialect=pg))
    str(delete(t).where(t.c.file_id == "f").compile(dialect=pg))
