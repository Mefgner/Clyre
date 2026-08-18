import os
import sqlite3
import tempfile
import uuid

from db_migrations import run_migrations

_EXPECTED_TABLES = {
    "alembic_version",
    "chunk_vector",
    "file_has_project",
    "file_has_thread",
    "file_metadata",
    "local_connection",
    "message",
    "project",
    "role",
    "role_has_user",
    "thread",
    "refresh_token",
    "user",
    "vector_index_meta",
}


def _fresh_db_url() -> str:
    path = os.path.join(tempfile.gettempdir(), f"clyre_mig_{uuid.uuid4().hex}.sqlite3")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{path}"
    return path


def _tables(path: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {name for (name,) in rows}
    finally:
        conn.close()


def _cleanup(path: str) -> None:
    os.environ.pop("DATABASE_URL", None)
    for p in (path, path + "-wal", path + "-shm"):
        if os.path.exists(p):
            os.remove(p)


def test_migrations_create_full_schema():
    path = _fresh_db_url()
    try:
        run_migrations()
        assert _EXPECTED_TABLES <= _tables(path)
    finally:
        _cleanup(path)


def test_migrations_are_idempotent():
    path = _fresh_db_url()
    try:
        run_migrations()
        run_migrations()
        assert _EXPECTED_TABLES <= _tables(path)
    finally:
        _cleanup(path)
