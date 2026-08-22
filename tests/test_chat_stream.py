"""NDJSON wire-contract tests for POST /api/chat/stream.

Pins the full contract including thinking blocks: enableThinking request flag,
new_thinking_chunk events, Message.thinking_value persistence, and the
model-card rule that thinking never re-enters the LLM history. Also covers the
decoupled-generation registry: offset replay, disconnect tolerance, eviction.
"""

import asyncio
import json
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

import db
import services.chatting as chatting_module
from app import app
from models import Base, GenerationRunRow, Message, Thread, User
from schemas.general import TokenPayload
from services.generation import (
    GenerationConflict,
    GenerationRun,
    get_run,
    sweep_interrupted_runs,
)
from utils import timing, web

CHUNKS = ["Hello", " world"]
THINKING_CHUNKS = [("thinking", "chain"), ("thinking", " of"), ("content", "Answer")]


class FakePipeline:
    def __init__(self, chunks):
        self._chunks = [
            chunk if isinstance(chunk, tuple) else ("content", chunk) for chunk in chunks
        ]
        self.calls = []
        self.sync_calls = []

    async def chat_completion_sync(self, history, **kwargs):
        self.sync_calls.append(dict(kwargs))
        return {"choices": [{"message": {"content": "Test Thread Title"}}]}

    async def chat_completion_stream(self, history, **kwargs):
        self.calls.append({"history": list(history), **kwargs})
        for chunk in self._chunks:
            yield chunk


class ExplodingPipeline(FakePipeline):
    async def chat_completion_stream(self, history, **kwargs):
        raise RuntimeError("llama exploded")
        yield  # pragma: no cover


class SlowPipeline(FakePipeline):
    async def chat_completion_stream(self, history, **kwargs):
        self.calls.append({"history": list(history), **kwargs})
        for chunk in self._chunks:
            await asyncio.sleep(0.2)
            yield chunk


def parse_events(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


async def fetch_messages(thread_id: str) -> list[Message]:
    maker = db.get_session_manager().async_session_maker
    async with maker() as session:
        result = await session.execute(
            select(Message).where(Message.thread_id == thread_id).order_by(Message.order)
        )
        return list(result.scalars().all())


@pytest_asyncio.fixture
async def tables():
    engine = db.get_session_manager().async_engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def user_id(tables) -> str:
    async with db.get_session_manager().async_session_maker() as session:
        user = User()
        session.add(user)
        await session.commit()
        return user.id


@pytest_asyncio.fixture
async def client(user_id, monkeypatch):
    fake = FakePipeline(CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: fake)

    async def _auth() -> TokenPayload:
        return TokenPayload(
            user_id=user_id,
            timestamp=timing.get_utc_now().timestamp(),
            refresh_token_id=None,
        )

    app.dependency_overrides[web.extract_access_token] = _auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http, fake
    app.dependency_overrides.pop(web.extract_access_token, None)


async def test_stream_requires_auth(tables):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        missing = await http.post("/api/chat/stream", json={"message": "Hi"})
        malformed = await http.post(
            "/api/chat/stream",
            json={"message": "Hi"},
            headers={"Authorization": "Bearer not-a-jwt"},
        )
    assert missing.status_code == 401
    assert malformed.status_code == 401


async def test_stream_event_order_new_thread(client):
    http, _ = client
    response = await http.post("/api/chat/stream", json={"message": "Hi"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"

    events = parse_events(response.text)
    assert [event["event"] for event in events] == [
        "user_message_insert",
        "new_chunk",
        "new_chunk",
        "assistant_message_insert",
        "done",
    ]
    thread_id = events[0]["threadId"]
    assert thread_id
    assert [event["chunk"] for event in events if event["event"] == "new_chunk"] == CHUNKS
    assert events[3]["threadId"] == thread_id
    assert events[4]["threadId"] is None


async def test_stream_persists_user_and_assistant_messages(client):
    http, fake = client
    response = await http.post("/api/chat/stream", json={"message": "Hi"})
    thread_id = parse_events(response.text)[0]["threadId"]

    messages = await fetch_messages(thread_id)
    assert [(m.role, m.inline_value, m.order) for m in messages] == [
        ("user", "Hi", 0),
        ("assistant", "".join(CHUNKS), 1),
    ]

    # Title generation must never pay the reasoning latency (known issue #18).
    assert fake.sync_calls[0]["enable_thinking"] is False


async def test_stream_existing_thread_sends_history_and_appends(client):
    http, fake = client
    first = await http.post("/api/chat/stream", json={"message": "Hi"})
    thread_id = parse_events(first.text)[0]["threadId"]

    second = await http.post(
        "/api/chat/stream", json={"message": "Again", "threadId": thread_id}
    )
    events = parse_events(second.text)
    assert events[0]["threadId"] == thread_id

    assert fake.calls[1]["history"] == [
        {"role": "system", "content": chatting_module.DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "".join(CHUNKS)},
        {"role": "user", "content": "Again"},
    ]

    messages = await fetch_messages(thread_id)
    assert [m.order for m in messages] == [0, 1, 2, 3]
    assert messages[2].inline_value == "Again"
    assert messages[3].inline_value == "".join(CHUNKS)


async def test_thinking_stream_events_and_persistence(user_id, monkeypatch, tables):
    fake = FakePipeline(THINKING_CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: fake)

    async def _auth() -> TokenPayload:
        return TokenPayload(
            user_id=user_id,
            timestamp=timing.get_utc_now().timestamp(),
            refresh_token_id=None,
        )

    app.dependency_overrides[web.extract_access_token] = _auth
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.post(
                "/api/chat/stream",
                json={"message": "Hard question", "enableThinking": True},
            )
            assert response.status_code == 200

            events = parse_events(response.text)
            kinds = [event["event"] for event in events]
            assert kinds == [
                "user_message_insert",
                "new_thinking_chunk",
                "new_thinking_chunk",
                "new_chunk",
                "assistant_message_insert",
                "done",
            ]
            assert [event["chunk"] for event in events[1:4]] == [
                "chain",
                " of",
                "Answer",
            ]

            assert fake.calls[0].get("enable_thinking") is True

            thread_id = events[0]["threadId"]
            messages = await fetch_messages(thread_id)
            assistant = messages[-1]
            assert assistant.inline_value == "Answer"
            assert assistant.thinking_value == "chain of"

            history_response = await http.get(f"/api/thread/{thread_id}")
            assert history_response.status_code == 200
            payload = history_response.json()
            by_role = {m["role"]: m for m in payload["messages"]}
            assert by_role["assistant"]["thinking"] == "chain of"
            assert by_role["user"]["thinking"] is None
    finally:
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_history_excludes_thinking_from_llm_payload(user_id, monkeypatch, tables):
    fake = FakePipeline(THINKING_CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: fake)

    async def _auth() -> TokenPayload:
        return TokenPayload(
            user_id=user_id,
            timestamp=timing.get_utc_now().timestamp(),
            refresh_token_id=None,
        )

    app.dependency_overrides[web.extract_access_token] = _auth
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            first = await http.post(
                "/api/chat/stream",
                json={"message": "Hard question", "enableThinking": True},
            )
            thread_id = parse_events(first.text)[0]["threadId"]

            await http.post(
                "/api/chat/stream", json={"message": "Follow-up", "threadId": thread_id}
            )

            assert fake.calls[1]["history"] == [
                {"role": "system", "content": chatting_module.DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": "Hard question"},
                {"role": "assistant", "content": "Answer"},
                {"role": "user", "content": "Follow-up"},
            ]
    finally:
        app.dependency_overrides.pop(web.extract_access_token, None)


def test_streaming_block_schema_rejects_unknown_event():
    from pydantic import ValidationError

    from schemas.chatting import StreamingBlock

    with pytest.raises(ValidationError):
        StreamingBlock.model_validate({"chunk": None, "event": "unknown_event"})


async def test_replay_from_offset_zero_is_identical(client):
    http, _ = client
    response = await http.post("/api/chat/stream", json={"message": "Hi"})
    thread_id = parse_events(response.text)[0]["threadId"]

    run = get_run(thread_id)
    assert run is not None
    await run.wait_done()

    replayed = [line async for line in run.subscribe(0)]
    assert "".join(replayed) == response.text


async def test_replay_from_mid_offset_yields_tail_only(client):
    http, _ = client
    response = await http.post("/api/chat/stream", json={"message": "Hi"})
    events = parse_events(response.text)
    thread_id = events[0]["threadId"]

    run = get_run(thread_id)
    assert run is not None
    await run.wait_done()

    tail = parse_events("".join([line async for line in run.subscribe(3)]))
    assert [event["event"] for event in tail] == ["assistant_message_insert", "done"]


async def test_disconnect_does_not_stop_generation(client, user_id):
    http, _ = client
    async with httpx.AsyncClient(transport=http._transport, base_url="http://test") as short:
        async with short.stream(
            "POST", "/api/chat/stream", json={"message": "Survive me"}
        ) as response:
            first_line = ""
            async for line in response.aiter_lines():
                first_line = line
                break

    thread_id = json.loads(first_line)["threadId"]
    run = get_run(thread_id)
    assert run is not None
    await run.wait_done()
    assert run.status.value == "finished"
    assert run.response == "".join(CHUNKS)

    messages = await fetch_messages(thread_id)
    assert messages[-1].role == "assistant"
    assert messages[-1].inline_value == "".join(CHUNKS)


async def test_run_evicted_after_grace_delay(client, monkeypatch):
    import services.generation as generation_module

    monkeypatch.setattr(generation_module, "EVENTS_GRACE_SECONDS", 0.05)
    http, _ = client
    response = await http.post("/api/chat/stream", json={"message": "Hi"})
    thread_id = parse_events(response.text)[0]["threadId"]

    run = get_run(thread_id)
    assert run is not None
    await run.wait_done()
    assert get_run(thread_id) is run

    await asyncio.sleep(generation_module.EVENTS_GRACE_SECONDS + 0.1)
    assert get_run(thread_id) is None


async def _fetch_journal_row(journal_id: str):
    maker = db.get_session_manager().async_session_maker
    async with maker() as session:
        return await session.get(GenerationRunRow, journal_id)


async def test_journal_row_transitions_to_finished(client, user_id):
    http, _ = client
    response = await http.post("/api/chat/stream", json={"message": "Hi"})
    thread_id = parse_events(response.text)[0]["threadId"]

    run = get_run(thread_id)
    assert run is not None
    assert run.journal_id is not None
    await run.wait_done()

    row = await _fetch_journal_row(run.journal_id)
    assert row is not None
    assert row.status == "finished"
    assert row.thread_id == thread_id
    assert row.user_id == user_id


async def test_failed_generation_marks_journal_and_drops_empty_message(
    user_id, monkeypatch, tables
):
    fake = ExplodingPipeline(CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: fake)

    async def _auth() -> TokenPayload:
        return TokenPayload(
            user_id=user_id,
            timestamp=timing.get_utc_now().timestamp(),
            refresh_token_id=None,
        )

    app.dependency_overrides[web.extract_access_token] = _auth
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.post("/api/chat/stream", json={"message": "Boom"})
            thread_id = parse_events(response.text)[0]["threadId"]
            run = get_run(thread_id)
            assert run is not None
            assert run.journal_id is not None
            await run.wait_done()

            row = await _fetch_journal_row(run.journal_id)
            assert row is not None
            assert row.status == "failed"

            messages = await fetch_messages(thread_id)
            assert [m.role for m in messages] == ["user"]
    finally:
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_sweep_marks_running_rows_interrupted(user_id, tables):
    async with db.get_session_manager().async_session_maker() as session:
        from crud import create_generation_run

        thread = Thread(id=uuid.uuid4().hex, user_id=user_id, title="t")
        session.add(thread)
        await session.flush()
        row = await create_generation_run(session, thread.id, user_id)
        await session.commit()
        orphan_id = row.id

    swept = await sweep_interrupted_runs()
    assert swept >= 1

    async with db.get_session_manager().async_session_maker() as session:
        row = await session.get(GenerationRunRow, orphan_id)
        assert row is not None
        assert row.status == "interrupted"


async def test_thread_metadata_exposes_is_generating(user_id, tables, monkeypatch):
    slow = SlowPipeline(CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: slow)

    async with db.get_session_manager().async_session_maker() as session:
        thread = Thread(id=uuid.uuid4().hex, user_id=user_id, title="t")
        session.add(thread)
        await session.commit()
        thread_id = thread.id

        run = await chatting_module.ChattingService().start_generation(
            session, thread_id, user_id, "Still working"
        )

        def _auth() -> TokenPayload:
            return TokenPayload(
                user_id=user_id,
                timestamp=timing.get_utc_now().timestamp(),
                refresh_token_id=None,
            )

        app.dependency_overrides[web.extract_access_token] = _auth
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
                meta = (await http.get(f"/api/thread/{thread_id}")).json()
                assert meta["isGenerating"] is True

                await run.wait_done()

                meta = (await http.get(f"/api/thread/{thread_id}")).json()
                assert meta["isGenerating"] is False
        finally:
            app.dependency_overrides.pop(web.extract_access_token, None)


async def _start_slow_generation(user_id: str, thread_id: str) -> GenerationRun:
    async with db.get_session_manager().async_session_maker() as session:
        return await chatting_module.ChattingService().start_generation(
            session, thread_id, user_id, "Slow question"
        )


async def _create_thread(user_id: str) -> str:
    async with db.get_session_manager().async_session_maker() as session:
        thread = Thread(id=uuid.uuid4().hex, user_id=user_id, title="t")
        session.add(thread)
        await session.commit()
        return thread.id


async def test_system_prompt_injected_once_at_stable_position(client):
    http, fake = client
    await http.post("/api/chat/stream", json={"message": "Hi"})

    history = fake.calls[0]["history"]
    assert history[0] == {
        "role": "system",
        "content": chatting_module.DEFAULT_SYSTEM_PROMPT,
    }
    assert sum(1 for message in history if message["role"] == "system") == 1


async def test_second_send_while_running_returns_409(client, user_id, monkeypatch):
    slow = SlowPipeline(CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: slow)
    http, _ = client

    thread_id = await _create_thread(user_id)
    run = await _start_slow_generation(user_id, thread_id)

    response = await http.post(
        "/api/chat/stream", json={"message": "Second", "threadId": thread_id}
    )
    assert response.status_code == 409

    run.cancel()
    await run.wait_done()


async def test_stop_persists_partial_and_closes_stream(client, user_id, monkeypatch):
    slow = SlowPipeline(CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: slow)
    http, _ = client

    thread_id = await _create_thread(user_id)
    run = await _start_slow_generation(user_id, thread_id)
    await asyncio.sleep(0.35)

    stop_response = await http.post("/api/chat/stop", json={"threadId": thread_id})
    assert stop_response.status_code == 200

    await run.wait_done()
    assert run.status.value == "stopped"
    assert run.response == "Hello"

    tail = parse_events("".join([line async for line in run.subscribe(1)]))
    assert [event["event"] for event in tail] == [
        "new_chunk",
        "assistant_message_insert",
        "done",
    ]

    messages = await fetch_messages(thread_id)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[-1].inline_value == "Hello"


async def test_stop_without_active_generation_returns_409(client, user_id):
    http, _ = client
    thread_id = await _create_thread(user_id)

    response = await http.post("/api/chat/stop", json={"threadId": thread_id})
    assert response.status_code == 409


async def test_retry_replaces_trailing_assistant(client, user_id):
    http, fake = client
    first = await http.post("/api/chat/stream", json={"message": "Hi"})
    thread_id = parse_events(first.text)[0]["threadId"]

    retry_response = await http.post(
        "/api/chat/retry", json={"threadId": thread_id, "enableThinking": False}
    )
    assert retry_response.status_code == 200
    events = parse_events(retry_response.text)
    assert [event["event"] for event in events] == [
        "user_message_insert",
        "new_chunk",
        "new_chunk",
        "assistant_message_insert",
        "done",
    ]

    messages = await fetch_messages(thread_id)
    assert [(m.role, m.order) for m in messages] == [("user", 0), ("assistant", 1)]
    assert messages[-1].inline_value == "".join(CHUNKS)

    assert len(fake.calls) == 2
    assert fake.calls[1]["history"] == [
        {"role": "system", "content": chatting_module.DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": "Hi"},
    ]


async def test_retry_without_assistant_message_returns_409(client, user_id):
    http, _ = client
    thread_id = await _create_thread(user_id)

    response = await http.post("/api/chat/retry", json={"threadId": thread_id})
    assert response.status_code == 409


async def test_stop_and_retry_require_auth(tables):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        stop = await http.post("/api/chat/stop", json={"threadId": str(uuid.uuid4())})
        retry = await http.post("/api/chat/retry", json={"threadId": str(uuid.uuid4())})
    assert stop.status_code == 401
    assert retry.status_code == 401


async def test_retry_nonexistent_thread_returns_400(client):
    http, _ = client
    response = await http.post("/api/chat/retry", json={"threadId": str(uuid.uuid4())})
    assert response.status_code == 400


async def test_retry_passes_enable_thinking_to_pipeline(client):
    http, fake = client
    first = await http.post("/api/chat/stream", json={"message": "Hi"})
    thread_id = parse_events(first.text)[0]["threadId"]

    retry_response = await http.post(
        "/api/chat/retry", json={"threadId": thread_id, "enableThinking": True}
    )
    assert retry_response.status_code == 200
    assert fake.calls[-1].get("enable_thinking") is True


async def test_sweep_is_idempotent_and_leaves_finished_rows(user_id, tables):
    from crud import create_generation_run
    from models import GenerationRunRow

    async with db.get_session_manager().async_session_maker() as session:
        thread = Thread(id=uuid.uuid4().hex, user_id=user_id, title="t")
        session.add(thread)
        await session.flush()
        orphan = await create_generation_run(session, thread.id, user_id)
        finished = await create_generation_run(session, thread.id, user_id)
        finished.status = "finished"
        await session.commit()
        orphan_id, finished_id = orphan.id, finished.id

    assert await sweep_interrupted_runs() >= 1

    async with db.get_session_manager().async_session_maker() as session:
        orphan_row = await session.get(GenerationRunRow, orphan_id)
        finished_row = await session.get(GenerationRunRow, finished_id)
        assert orphan_row is not None and orphan_row.status == "interrupted"
        assert finished_row is not None and finished_row.status == "finished"

    assert await sweep_interrupted_runs() >= 0

    async with db.get_session_manager().async_session_maker() as session:
        orphan_row = await session.get(GenerationRunRow, orphan_id)
        assert orphan_row is not None and orphan_row.status == "interrupted"


async def test_finalize_failure_does_not_wedge_run(user_id, monkeypatch, tables):
    """A DB failure at the terminal flush must not hang subscribers or leave
    the run RUNNING in the registry (thread 409-locked until restart)."""
    fake = FakePipeline(CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: fake)

    async def _boom(session, message, content, thinking):
        raise RuntimeError("db down at terminal flush")

    monkeypatch.setattr(chatting_module, "update_message_content", _boom)

    thread_id = await _create_thread(user_id)
    async with db.get_session_manager().async_session_maker() as session:
        run = await chatting_module.ChattingService().start_generation(
            session, thread_id, user_id, "Hi"
        )

    await run.wait_done()
    assert run.done is True
    assert run.status.value == "finished"

    replayed = [line async for line in run.subscribe(0)]
    assert parse_events("".join(replayed))[-1]["event"] == "done"


async def test_sweep_deletes_unwritten_reserved_rows(user_id, tables):
    """Crash recovery must remove reserved assistant rows that were never
    written — otherwise build_history sends a null assistant turn forever."""
    from crud import create_generation_run
    from crud.message import create_message, reserve_assistant_message

    async with db.get_session_manager().async_session_maker() as session:
        thread = Thread(id=uuid.uuid4().hex, user_id=user_id, title="t")
        session.add(thread)
        await session.flush()
        await create_generation_run(session, thread.id, user_id)
        await reserve_assistant_message(session, user_id=user_id, thread_id=thread.id, order=1)
        await create_message(
            session,
            user_id=user_id,
            thread_id=thread.id,
            role="assistant",
            content="survivor",
            order=2,
        )
        await session.commit()
        thread_id = thread.id

    assert await sweep_interrupted_runs() >= 1

    messages = await fetch_messages(thread_id)
    assert [(m.role, m.inline_value) for m in messages] == [("assistant", "survivor")]


async def test_foreign_active_thread_maps_to_not_found(user_id, monkeypatch, tables):
    """Ownership is checked before activity: a foreign thread id must yield
    'not found' (404), never a 409 that leaks generation state."""
    slow = SlowPipeline(CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: slow)

    async with db.get_session_manager().async_session_maker() as session:
        stranger = User()
        session.add(stranger)
        await session.commit()
        stranger_id = stranger.id

    thread_id = await _create_thread(user_id)
    run = await _start_slow_generation(user_id, thread_id)

    async with db.get_session_manager().async_session_maker() as session:
        with pytest.raises(ValueError):
            await chatting_module.ChattingService().start_generation(
                session, thread_id, stranger_id, "intruder"
            )

    run.cancel()
    await run.wait_done()


async def test_concurrent_starts_produce_single_winner(user_id, monkeypatch, tables):
    """Two sends racing on one thread: exactly one run may start; the loser
    gets GenerationConflict instead of orphaning the winner's run."""
    gate = asyncio.Event()

    class GatedPipeline(FakePipeline):
        async def chat_completion_stream(self, history, **kwargs):
            self.calls.append({"history": list(history), **kwargs})
            await gate.wait()
            for chunk in self._chunks:
                yield chunk

    fake = GatedPipeline(CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: fake)

    original_ensure = chatting_module.ChattingService._ensure_no_active

    async def _slow_ensure(self, session, thread_id):
        await asyncio.sleep(0.05)  # widen the historical race window
        await original_ensure(self, session, thread_id)

    monkeypatch.setattr(chatting_module.ChattingService, "_ensure_no_active", _slow_ensure)

    thread_id = await _create_thread(user_id)
    service = chatting_module.ChattingService()

    async def _send(message):
        async with db.get_session_manager().async_session_maker() as session:
            return await service.start_generation(session, thread_id, user_id, message)

    winner, loser = await asyncio.gather(
        _send("first"), _send("second"), return_exceptions=True
    )
    assert isinstance(winner, GenerationRun) or isinstance(loser, GenerationRun)
    conflicts = [r for r in (winner, loser) if isinstance(r, GenerationConflict)]
    assert len(conflicts) == 1

    messages = await fetch_messages(thread_id)
    assert [m.role for m in messages if m.role == "user"] == ["user"]

    gate.set()
    run = winner if isinstance(winner, GenerationRun) else loser
    assert isinstance(run, GenerationRun)
    await run.wait_done()
    assert run.status.value == "finished"


async def test_delete_thread_stops_active_generation(user_id, monkeypatch, tables):
    """Deleting a generating thread must stop its run — the background task
    otherwise flushes into rows the cascade delete removed."""
    slow = SlowPipeline(CHUNKS)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda tier: slow)

    thread_id = await _create_thread(user_id)
    run = await _start_slow_generation(user_id, thread_id)

    from services.thread import ThreadService

    async with db.get_session_manager().async_session_maker() as session:
        await ThreadService.delete_thread(session, user_id, thread_id)

    await run.wait_done()
    assert run.status.value == "stopped"
