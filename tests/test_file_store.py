import pytest

from pipelines.fs import LocalFileStore


@pytest.fixture
def store(tmp_path):
    return LocalFileStore(tmp_path)


async def test_save_read_roundtrip(store):
    await store.save("u1", "f1", b"hello bytes")
    assert await store.read("u1", "f1") == b"hello bytes"


async def test_users_are_isolated(store):
    await store.save("u1", "f1", b"a")
    await store.save("u2", "f1", b"b")
    assert await store.read("u1", "f1") == b"a"
    assert await store.read("u2", "f1") == b"b"


async def test_delete_removes_file(store):
    await store.save("u1", "f1", b"x")
    await store.delete("u1", "f1")
    with pytest.raises(FileNotFoundError):
        await store.read("u1", "f1")


async def test_delete_is_idempotent(store):
    await store.delete("u1", "missing")
