"""Live e2e fixtures: the in-process app against dockerized Postgres + llama.cpp.

Bring the stack up first (see README "Running e2e tests"):
    docker compose -f docker-compose.e2e.yml up -d

Environment must be finalised before anything imports db/app — the database
engine is built as an import side effect. Real environment variables win over
the repo `.env` file, so `CLYRE_E2E_*` overrides work as expected.
"""

import os

os.environ.setdefault("DB_ENGINE", "postgresql")
os.environ.setdefault(
    "DATABASE_URL",
    os.getenv(
        "CLYRE_E2E_DATABASE_URL",
        "postgresql+asyncpg://clyre_e2e:clyre_e2e@localhost:55432/clyre_e2e",
    ),
)
os.environ.setdefault(
    "SMALL_BASE_URL", os.getenv("CLYRE_E2E_CHAT_URL", "http://localhost:6760")
)
# 4B deliberately sits below the project's 9B chat floor: e2e needs a model
# that fits the 4GB VRAM of the test GPU alongside acceptable run times.
os.environ.setdefault("SMALL_MODEL", "Qwen3.5-4B")
os.environ.setdefault(
    "EMBEDDING_BASE_URL", os.getenv("CLYRE_E2E_EMBEDDING_URL", "http://localhost:6761")
)
os.environ.setdefault("EMBEDDING_MODEL", "Qwen3-Embedding-0.6B")
os.environ.setdefault("VECTOR_DIM", "1024")
os.environ.setdefault("HASHING_SECRET", "clyre-e2e-hashing-secret")
os.environ.setdefault("ACCESS_TOKEN_SECRET", "clyre-e2e-access-token-secret")

import asyncio
import socket
from collections.abc import AsyncIterator
from typing import NamedTuple
from uuid import uuid4

import httpx
import pytest_asyncio
import uvicorn
from sqlalchemy import select

import db
from crud.vector import get_vector_repository
from models import Base, LocalConnection

# Generations on CPU can take minutes; streaming reads need a patient client.
CLIENT_TIMEOUT = httpx.Timeout(900.0)


class AuthContext(NamedTuple):
    headers: dict[str, str]
    user_id: str
    email: str


async def _ensure_schema() -> None:
    engine = db.get_session_manager().async_engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await get_vector_repository().ensure_schema(engine)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator[httpx.AsyncClient]:
    """App served by a real uvicorn listener on an ephemeral port.

    httpx.ASGITransport cannot be used here: it runs the ASGI app to completion
    and returns the whole buffered body at once, so clients observe the first
    chunk only after the response finished — killing live-streaming semantics
    (mid-generation stop/conflict, concurrent requests on open streams).
    Uvicorn runs on the test's event loop; lifespan stays off because the
    startup/shutdown handlers are driven manually below.
    """
    await _ensure_schema()
    from app import app

    # ASGITransport does not drive lifespan; run the registered handlers.
    await app.router.startup()

    config = uvicorn.Config(
        app, host="127.0.0.1", port=_free_port(), log_level="warning", lifespan="off"
    )
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    for _ in range(200):  # wait up to 10 s for the listener
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:
        serve_task.cancel()
        raise RuntimeError("uvicorn failed to start")

    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{config.port}", timeout=CLIENT_TIMEOUT
    ) as http:
        yield http

    server.should_exit = True
    await serve_task
    await app.router.shutdown()


@pytest_asyncio.fixture
async def auth(app_client: httpx.AsyncClient) -> AsyncIterator[AuthContext]:
    """Register a fresh user through the real /api/auth flow."""
    suffix = uuid4().hex[:8]
    # gmail.com passes the backend's DNS-deliverability check (example.com has
    # no MX record and is rejected); no mail is ever sent to it.
    email = f"clyre.e2e.{suffix}@gmail.com"
    response = await app_client.post(
        "/api/auth/register",
        json={
            "name": f"e2e_user_{suffix}",
            "email": email,
            "password": "E2e_Secret1!",
        },
    )
    assert response.status_code == 201, response.text

    maker = db.get_session_manager().async_session_maker
    async with maker() as session:
        connection = (
            await session.execute(select(LocalConnection).where(LocalConnection.email == email))
        ).scalar_one()
        user_id = connection.user_id

    yield AuthContext(
        headers={"Authorization": f"Bearer {response.json()['token']}"},
        user_id=user_id,
        email=email,
    )
