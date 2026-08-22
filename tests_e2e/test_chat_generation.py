"""Live e2e for chat generation over the real NDJSON API against dockerized
Postgres + llama.cpp (Qwen3.5-4B): reasoning on/off, stop, retry, conflicts.

Requires the e2e stack: `docker compose -f docker-compose.e2e.yml up -d`.
"""

import uuid

import httpx
import pytest
from conftest import AuthContext
from helpers import (
    CHUNK_EVENTS,
    assert_stream_contract,
    chunk_texts,
    drain_events,
    iter_events,
    open_stream,
)
from sqlalchemy import select

import db
from models import GenerationRunRow, Message
from services.chatting import ChattingService
from services.generation import GenerationStatus, get_run

pytestmark = pytest.mark.e2e

REASONING_PROMPT = "What is 17 * 24? Reason step by step carefully, then give the final number."
LONG_PROMPT = (
    "Write a long story (at least 500 words) about a lighthouse keeper who "
    "discovers a mysterious door in the cliff."
)


async def _thread_messages(thread_id: str) -> list[Message]:
    maker = db.get_session_manager().async_session_maker
    async with maker() as session:
        rows = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.thread_id == thread_id)
                    .order_by(Message.order)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


async def test_stream_with_thinking(app_client: httpx.AsyncClient, auth: AuthContext):
    async with open_stream(
        app_client,
        "/api/chat/stream",
        headers=auth.headers,
        json_body={"message": REASONING_PROMPT, "enableThinking": True},
    ) as response:
        events = await drain_events(response)

    thread_id = assert_stream_contract(events)
    assert chunk_texts(events, "new_thinking_chunk"), "expected thinking output"
    assert chunk_texts(events, "new_chunk"), "expected answer content"

    messages = await _thread_messages(thread_id)
    assistant = [message for message in messages if message.role == "assistant"]
    assert len(assistant) == 1
    assert assistant[0].inline_value
    assert assistant[0].thinking_value


async def test_stream_without_thinking(app_client: httpx.AsyncClient, auth: AuthContext):
    async with open_stream(
        app_client,
        "/api/chat/stream",
        headers=auth.headers,
        json_body={"message": REASONING_PROMPT, "enableThinking": False},
    ) as response:
        events = await drain_events(response)

    assert_stream_contract(events)
    assert not chunk_texts(events, "new_thinking_chunk"), "thinking must be disabled explicitly"
    assert chunk_texts(events, "new_chunk")


async def _read_until_first_chunk(
    response: httpx.Response,
) -> str:
    """Consume one open LONG-generation stream up to its first content chunk."""
    thread_id: str | None = None
    async for event in iter_events(response):
        if event["event"] == "user_message_insert":
            thread_id = event["threadId"]
        elif event["event"] in CHUNK_EVENTS:
            break
    assert thread_id
    return thread_id


async def test_stream_conflict_while_active(app_client: httpx.AsyncClient, auth: AuthContext):
    """A second generation on a busy thread must be rejected with 409."""
    async with open_stream(
        app_client,
        "/api/chat/stream",
        headers=auth.headers,
        json_body={"message": LONG_PROMPT},
    ) as response:
        thread_id = await _read_until_first_chunk(response)

        conflict = await app_client.post(
            "/api/chat/stream",
            json={"message": "hello again", "threadId": thread_id},
            headers=auth.headers,
        )
        assert conflict.status_code == 409

    # Unsubscribe-by-disconnect must NOT kill the run; stop it cleanly.
    stop = await app_client.post(
        "/api/chat/stop", json={"threadId": thread_id}, headers=auth.headers
    )
    assert stop.status_code == 200
    run = get_run(thread_id)
    assert run is not None
    await run.wait_done()


async def test_stop_mid_generation(app_client: httpx.AsyncClient, auth: AuthContext):
    received: list[dict] = []
    thread_id: str | None = None
    async with open_stream(
        app_client,
        "/api/chat/stream",
        headers=auth.headers,
        json_body={"message": LONG_PROMPT},
    ) as response:
        async for event in iter_events(response):
            received.append(event)
            if event["event"] in CHUNK_EVENTS and thread_id is not None:
                break
            if event["event"] == "user_message_insert":
                thread_id = event["threadId"]
    assert thread_id
    assert chunk_texts(received, "new_chunk") or chunk_texts(received, "new_thinking_chunk")

    stopped = await app_client.post(
        "/api/chat/stop", json={"threadId": thread_id}, headers=auth.headers
    )
    assert stopped.status_code == 200
    assert stopped.json() == {"result": "stopping"}

    again = await app_client.post(
        "/api/chat/stop", json={"threadId": thread_id}, headers=auth.headers
    )
    # Deliberate contract: request_stop() is idempotent — the second stop in
    # the stopping window reports "no active generation" (409), not 200.
    assert again.status_code == 409

    run = get_run(thread_id)
    assert run is not None
    await run.wait_done()
    assert run.status is GenerationStatus.STOPPED

    maker = db.get_session_manager().async_session_maker
    async with maker() as session:
        row = await session.get(GenerationRunRow, run.journal_id)
    assert row is not None and row.status == "stopped"

    # A stopped generation frees the thread: the next one must start cleanly.
    async with open_stream(
        app_client,
        "/api/chat/stream",
        headers=auth.headers,
        json_body={
            "message": "Answer with a single word only: ok.",
            "threadId": thread_id,
        },
    ) as response:
        follow_up = await drain_events(response)
    assert_stream_contract(follow_up)


async def test_retry_regenerates_in_place(app_client: httpx.AsyncClient, auth: AuthContext):
    async with open_stream(
        app_client,
        "/api/chat/stream",
        headers=auth.headers,
        json_body={"message": REASONING_PROMPT},
    ) as response:
        first_events = await drain_events(response)
    thread_id = assert_stream_contract(first_events)

    messages_before = await _thread_messages(thread_id)
    assert [message.role for message in messages_before] == ["user", "assistant"]

    retry_response = await app_client.post(
        "/api/chat/retry", json={"threadId": thread_id}, headers=auth.headers
    )
    assert retry_response.status_code == 200
    retry_events = await drain_events(retry_response)
    assert_stream_contract(retry_events)
    assert chunk_texts(retry_events, "new_chunk")

    messages_after = await _thread_messages(thread_id)
    assert len(messages_after) == len(messages_before)
    assert messages_after[-1].role == "assistant"
    assert messages_after[-1].order == messages_before[-1].order
    assert messages_after[-1].inline_value


async def test_retry_conflicts_while_active(app_client: httpx.AsyncClient, auth: AuthContext):
    async with open_stream(
        app_client,
        "/api/chat/stream",
        headers=auth.headers,
        json_body={"message": LONG_PROMPT},
    ) as response:
        thread_id = await _read_until_first_chunk(response)

        conflict = await app_client.post(
            "/api/chat/retry", json={"threadId": thread_id}, headers=auth.headers
        )
        assert conflict.status_code == 409

    stop = await app_client.post(
        "/api/chat/stop", json={"threadId": thread_id}, headers=auth.headers
    )
    assert stop.status_code == 200


async def test_retry_nothing_to_retry(app_client: httpx.AsyncClient, auth: AuthContext):
    """A thread whose last message is not an assistant reply has nothing to retry."""
    service = ChattingService()
    maker = db.get_session_manager().async_session_maker
    async with maker() as session:
        _, thread_id = await service.save_message(
            session, auth.user_id, "A question nobody answered yet.", "user"
        )

    conflict = await app_client.post(
        "/api/chat/retry", json={"threadId": thread_id}, headers=auth.headers
    )
    assert conflict.status_code == 409


async def test_stop_without_generation(app_client: httpx.AsyncClient, auth: AuthContext):
    missing_thread = uuid.uuid4()
    response = await app_client.post(
        "/api/chat/stop",
        json={"threadId": str(missing_thread)},
        headers=auth.headers,
    )
    assert response.status_code == 404
