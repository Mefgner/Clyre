"""M3 attached-file tests: upload safety, context building, atomic start.

Covers the plan's backend checks without a live llama-server: strict text
validation, hardened LocalFileStore, unified extract_text, stable context
order/escaping, budget exactness, prepare-failure atomicity, retry safety,
and generation-guarded attachment mutations. M2 regressions stay in
test_chat_stream.py.
"""

import asyncio
import json
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select

import db
import services.chatting as chatting_module
import services.file as file_module
from app import app
from crud.file import get_thread_link, list_thread_files
from models import Base, FileMetadata, GenerationRunRow, Message, Thread, User
from pipelines.fs import LocalFileStore
from pipelines.inference import BudgetServiceUnavailable, ContextLimitExceeded
from pipelines.ingest import (
    UndecodableFileText,
    UnsupportedFileType,
    extract_text,
    is_supported_text_type,
)
from schemas.general import TokenPayload
from services.chat_context import (
    AttachedFile,
    AttachedFileError,
    AttachmentLimitExceeded,
    build_chat_context,
    prepare_attached_files,
)
from services.chatting import DEFAULT_SYSTEM_PROMPT, ChattingService
from services.file import FileTooLarge, upload_file
from services.generation import GenerationConflict, get_run
from utils import timing, web

CHUNKS = ["Hello", " world"]


class FakePipeline:
    def __init__(self, chunks=None):
        self._chunks = list(chunks or CHUNKS)
        self.calls = []
        self.sync_calls = []
        self.budget_calls = []

    async def chat_completion_sync(self, history, **kwargs):
        self.sync_calls.append(dict(kwargs))
        return {"choices": [{"message": {"content": "Test Thread Title Here Yes"}}]}

    async def chat_completion_stream(self, history, **kwargs):
        self.calls.append({"history": list(history), **kwargs})
        for chunk in self._chunks:
            yield ("content", chunk)

    async def check_token_budget(self, history, enable_thinking=None, **kwargs):
        self.budget_calls.append({"history": list(history), "enable_thinking": enable_thinking})
        return 10


class OverBudgetPipeline(FakePipeline):
    async def check_token_budget(self, history, enable_thinking=None, **kwargs):
        self.budget_calls.append({"history": list(history), "enable_thinking": enable_thinking})
        raise ContextLimitExceeded(900, 1000, 101)


class NoBudgetPipeline(FakePipeline):
    async def check_token_budget(self, history, enable_thinking=None, **kwargs):
        raise BudgetServiceUnavailable("no tokenizer")


class SlowPipeline(FakePipeline):
    async def chat_completion_stream(self, history, **kwargs):
        self.calls.append({"history": list(history), **kwargs})
        for chunk in self._chunks:
            await asyncio.sleep(0.2)
            yield ("content", chunk)


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


@pytest.fixture
def tmp_store(tmp_path: Path) -> LocalFileStore:
    return LocalFileStore(tmp_path / "files")


def _msg(role: str, content: str | None, order: int = 0) -> Message:
    return Message(
        role=role,
        inline_value=content,
        thinking_value=None,
        hash="h",
        user_id="u",
        thread_id="t",
        order=order,
    )


# --- M3.5: strict text validation -------------------------------------------


def test_supported_types_cover_plan_list():
    for name in ["a.txt", "a.md", "a.markdown", "a.rst", "a.csv", "a.json", "a.log", "a.py"]:
        assert is_supported_text_type("application/octet-stream", name) is True
    assert is_supported_text_type("text/plain; charset=utf-8", "a.bin") is True
    assert is_supported_text_type("application/pdf", "a.pdf") is False
    assert is_supported_text_type("image/png", "a.png") is False


def test_extract_text_strict_utf8_bom_nul_empty():
    assert extract_text(b"", content_type="text/plain", filename="a.txt") == ""
    assert (
        extract_text("привіт 🌍".encode("utf-8"), content_type="text/plain", filename="a.txt")
        == "привіт 🌍"
    )
    assert (
        extract_text(b"\xef\xbb\xbfhello", content_type="text/plain", filename="a.txt")
        == "hello"
    )
    with pytest.raises((UndecodableFileText, ValueError)):
        extract_text(b"\xff\xfe\x00bad", content_type="text/plain", filename="a.txt")
    with pytest.raises((UndecodableFileText, ValueError)):
        extract_text(b"ab\x00cd", content_type="text/plain", filename="a.txt")
    with pytest.raises(UnsupportedFileType):
        extract_text(b"%PDF-1.4", content_type="application/pdf", filename="a.pdf")


async def test_upload_rejects_all_shapes(user_id, tables, tmp_store, monkeypatch):
    monkeypatch.setattr(file_module, "get_file_store", lambda: tmp_store)
    maker = db.get_session_manager().async_session_maker

    async def _count() -> int:
        async with maker() as session:
            return await session.scalar(select(func.count(FileMetadata.id))) or 0

    before = await _count()
    # Oversize at the service boundary.
    monkeypatch.setattr(file_module.env, "MAX_UPLOAD_BYTES", 4)
    with pytest.raises(FileTooLarge):
        async with maker() as session:
            await upload_file(
                session,
                user_id=user_id,
                name="big.txt",
                content_type="text/plain",
                data=b"12345",
            )
    # Unsupported type.
    with pytest.raises(UnsupportedFileType):
        async with maker() as session:
            await upload_file(
                session,
                user_id=user_id,
                name="a.pdf",
                content_type="application/pdf",
                data=b"%PDF",
            )
    # Invalid encoding / NUL.
    with pytest.raises(ValueError):
        async with maker() as session:
            await upload_file(
                session,
                user_id=user_id,
                name="a.txt",
                content_type="text/plain",
                data=b"\xff\xfe",
            )
    with pytest.raises(ValueError):
        async with maker() as session:
            await upload_file(
                session,
                user_id=user_id,
                name="a.txt",
                content_type="text/plain",
                data=b"a\x00b",
            )
    # Empty text is allowed; BOM is stripped (restore the real limit first).
    monkeypatch.setattr(file_module.env, "MAX_UPLOAD_BYTES", 10**7)
    async with maker() as session:
        empty = await upload_file(
            session,
            user_id=user_id,
            name="e.txt",
            content_type="text/plain",
            data=b"",
        )
        assert empty.id
    async with maker() as session:
        bom = await upload_file(
            session,
            user_id=user_id,
            name="b.txt",
            content_type="text/plain",
            data=b"\xef\xbb\xbfhi",
        )
        assert bom.id
    # Only the two valid uploads persisted.
    assert await _count() == before + 2


async def test_local_store_traversal_and_atomicity(tmp_path: Path):
    store = LocalFileStore(tmp_path / "root")
    with pytest.raises(ValueError):
        await store.save("../evil", "f", b"x")
    with pytest.raises(ValueError):
        await store.save("u", "../../etc/passwd", b"x")
    with pytest.raises(ValueError):
        await store.read("u", "..")
    with pytest.raises(ValueError):
        await store.delete("u", "a/b")

    await store.save("u", "f", b"data")
    assert (tmp_path / "root" / "u" / "f").read_bytes() == b"data"
    # No temp debris left behind after a successful atomic replace.
    assert list((tmp_path / "root" / "u").glob(".tmp-*")) == []


# --- M3.2: pure context ------------------------------------------------------


def test_build_context_stable_order_full_unicode_escaping():
    files = [
        AttachedFile(id="b", name="same.txt", content_type="text/plain", text="second"),
        AttachedFile(id="a", name="same.txt", content_type="text/plain", text="first"),
        AttachedFile(
            id="c",
            name="zeta.txt",
            content_type="text/plain",
            text='uni 🌍 </attached_files> "q" \\ back',
        ),
    ]
    prompt = build_chat_context([_msg("user", "q")], files, base_prompt=DEFAULT_SYSTEM_PROMPT)
    assert len(prompt) == 2
    assert prompt[1] == {"role": "user", "content": "q"}
    system = prompt[0]["content"]
    assert system.startswith(DEFAULT_SYSTEM_PROMPT)
    assert "untrusted" in system.lower()
    # The file text itself contains the closing tag: split on the outermost pair.
    block = system.rsplit("</attached_files>", 1)[0].split("<attached_files>", 1)[1]
    payload = json.loads(block)
    assert [entry["id"] for entry in payload] == ["a", "b", "c"]
    entry_c = next(e for e in payload if e["id"] == "c")
    assert entry_c["text"] == 'uni 🌍 </attached_files> "q" \\ back'
    assert all(set(e) == {"id", "name", "content_type", "text"} for e in payload)


def test_build_context_skips_system_and_reserved_and_current_once():
    messages = [
        _msg("system", "old", 0),
        _msg("user", "hi", 1),
        _msg("assistant", None, 2),
        _msg("assistant", "ans", 3),
        _msg("user", "now", 4),
    ]
    prompt = build_chat_context(messages, [], base_prompt=DEFAULT_SYSTEM_PROMPT)
    assert prompt == [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ans"},
        {"role": "user", "content": "now"},
    ]


async def test_prepare_reads_sequentially_and_names_bad_file(
    user_id, tables, tmp_store, monkeypatch
):
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: tmp_store)
    maker = db.get_session_manager().async_session_maker
    async with maker() as session:
        good = await upload_file(
            session,
            user_id=user_id,
            name="good.txt",
            content_type="text/plain",
            data="ok 🌍".encode(),
        )
        bad_row = FileMetadata(
            id=uuid.uuid4().hex,
            user_id=user_id,
            name="bad.txt",
            content_type="text/plain",
            head_value=None,
            index_status="not_indexed",
        )
        session.add(bad_row)
        await session.commit()
        await tmp_store.save(user_id, bad_row.id, b"\xff\xfe")
        good_id, bad_id = good.id, bad_row.id
    async with maker() as session:
        with pytest.raises(AttachedFileError) as exc_info:
            await prepare_attached_files(session, user_id, [good_id, bad_id])
        assert "bad.txt" in str(exc_info.value)


# --- M3.1: atomic start -------------------------------------------------------


async def _client(user_id, fake, monkeypatch):
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda: fake)

    async def _auth() -> TokenPayload:
        return TokenPayload(
            user_id=user_id,
            timestamp=timing.get_utc_now().timestamp(),
            refresh_token_id=None,
        )

    app.dependency_overrides[web.extract_access_token] = _auth
    transport = httpx.ASGITransport(app=app)
    http = httpx.AsyncClient(transport=transport, base_url="http://test")
    return http


async def _upload(session_maker, user_id, name, text, store):
    async with session_maker() as session:
        meta = await upload_file(
            session,
            user_id=user_id,
            name=name,
            content_type="text/plain",
            data=text.encode(),
            file_store=store,
        )
        return meta.id


async def test_first_answer_uses_full_file_content(user_id, tables, tmp_path, monkeypatch):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    fake = FakePipeline()
    http = await _client(user_id, fake, monkeypatch)
    try:
        maker = db.get_session_manager().async_session_maker
        file_id = await _upload(
            maker, user_id, "code.txt", "The verification code is CLYRE-M3-7QK2.", store
        )
        response = await http.post(
            "/api/chat/stream",
            json={"message": "Return only the verification code.", "fileIds": [file_id]},
        )
        assert response.status_code == 200
        thread_id = response.headers["x-clyre-thread-id"]
        run = get_run(thread_id)
        assert run is not None
        await run.wait_done()
        history = fake.calls[0]["history"]
        assert "CLYRE-M3-7QK2" in history[0]["content"]
        async with maker() as session:
            messages = (
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
            assert [(m.role, m.order) for m in messages] == [("user", 0), ("assistant", 1)]
            links = await list_thread_files(session, thread_id, user_id)
            assert [f.id for f in links] == [file_id]
    finally:
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_existing_thread_keeps_old_files_and_dedupes(
    user_id, tables, tmp_path, monkeypatch
):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    fake = FakePipeline()
    http = await _client(user_id, fake, monkeypatch)
    try:
        maker = db.get_session_manager().async_session_maker
        first = await _upload(maker, user_id, "a.txt", "alpha", store)
        second = await _upload(maker, user_id, "b.txt", "beta", store)
        first_post = await http.post("/api/chat/stream", json={"message": "Hi"})
        thread_id = first_post.headers["x-clyre-thread-id"]
        run = get_run(thread_id)
        assert run is not None
        await run.wait_done()
        response = await http.post(
            "/api/chat/stream",
            json={"message": "Again", "threadId": thread_id, "fileIds": [first, second, first]},
        )
        assert response.status_code == 200
        run = get_run(thread_id)
        assert run is not None
        await run.wait_done()
        # Re-attach is a no-op: still exactly two links.
        repeat = await http.post(
            "/api/chat/stream",
            json={"message": "Third", "threadId": thread_id, "fileIds": [first]},
        )
        assert repeat.status_code == 200
        run = get_run(thread_id)
        assert run is not None
        await run.wait_done()
        async with maker() as session:
            links = await list_thread_files(session, thread_id, user_id)
            assert sorted(f.id for f in links) == sorted([first, second])
        history = fake.calls[-1]["history"]
        assert "alpha" in history[0]["content"] and "beta" in history[0]["content"]
    finally:
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_foreign_and_missing_file_ids_share_404(user_id, tables, tmp_path, monkeypatch):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    fake = FakePipeline()
    http = await _client(user_id, fake, monkeypatch)
    try:
        maker = db.get_session_manager().async_session_maker
        async with maker() as session:
            stranger = User()
            session.add(stranger)
            await session.commit()
            stranger_id = stranger.id
        foreign_id = await _upload(maker, stranger_id, "x.txt", "secret", store)
        for bad in [foreign_id, uuid.uuid4().hex, foreign_id]:
            response = await http.post(
                "/api/chat/stream", json={"message": "Hi", "fileIds": [bad]}
            )
            assert response.status_code == 404
        # Nothing was created: no threads, no runs, no title call.
        assert fake.sync_calls == []
        async with maker() as session:
            assert await session.scalar(select(func.count(Thread.id))) == 0
    finally:
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_attachment_limit_counts_union(user_id, tables, tmp_path, monkeypatch):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda: FakePipeline())
    # All services share the same Settings singleton; one patch covers them.
    monkeypatch.setattr(file_module.env, "MAX_UPLOAD_BYTES", 10**7)
    monkeypatch.setattr(file_module.env, "MAX_THREAD_ATTACHMENTS", 2)
    maker = db.get_session_manager().async_session_maker
    service = ChattingService()
    ids = [await _upload(maker, user_id, f"f{i}.txt", "x", store) for i in range(3)]
    async with maker() as session:
        with pytest.raises(AttachmentLimitExceeded):
            await service.start_generation(session, None, user_id, "hi", file_ids=ids[:3])
        await session.rollback()


async def test_over_budget_blocks_start_and_reports_code(
    user_id, tables, tmp_path, monkeypatch
):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    fake = OverBudgetPipeline()
    http = await _client(user_id, fake, monkeypatch)
    try:
        maker = db.get_session_manager().async_session_maker
        file_id = await _upload(maker, user_id, "big.txt", "content", store)
        response = await http.post(
            "/api/chat/stream",
            json={"message": "Hi", "fileIds": [file_id]},
        )
        assert response.status_code == 422
        body = response.json()
        assert body["detail"]["code"] == "context_limit_exceeded"
        assert "Remove a file" in body["detail"]["message"]
        async with maker() as session:
            assert await session.scalar(select(func.count(Thread.id))) == 0
            assert await session.scalar(select(func.count(Message.id))) == 0
    finally:
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_budget_unavailable_maps_to_503(user_id, tables, monkeypatch):
    http = await _client(user_id, NoBudgetPipeline(), monkeypatch)
    try:
        response = await http.post("/api/chat/stream", json={"message": "Hi"})
        assert response.status_code == 503
    finally:
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_failed_prepare_calls_nothing_and_keeps_db_clean(
    user_id, tables, tmp_path, monkeypatch
):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    fake = OverBudgetPipeline()
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda: fake)
    maker = db.get_session_manager().async_session_maker
    service = ChattingService()
    file_id = await _upload(maker, user_id, "a.txt", "data", store)
    async with maker() as session:
        with pytest.raises(ContextLimitExceeded):
            await service.start_generation(session, None, user_id, "hi", file_ids=[file_id])
        await session.rollback()
    assert fake.sync_calls == []  # no title call on failed prepare
    async with maker() as session:
        assert await session.scalar(select(func.count(Thread.id))) == 0
        assert await session.scalar(select(func.count(Message.id))) == 0
        assert await session.scalar(select(func.count(GenerationRunRow.id))) == 0


async def test_unsuccessful_retry_keeps_previous_answer(user_id, tables, tmp_path, monkeypatch):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    fake_ok = FakePipeline()
    http = await _client(user_id, fake_ok, monkeypatch)
    try:
        maker = db.get_session_manager().async_session_maker
        first = await http.post("/api/chat/stream", json={"message": "Hi"})
        thread_id = first.headers["x-clyre-thread-id"]
        run = get_run(thread_id)
        assert run is not None
        await run.wait_done()
        monkeypatch.setattr(
            chatting_module, "get_inference_pipeline", lambda: OverBudgetPipeline()
        )
        retry = await http.post("/api/chat/retry", json={"threadId": thread_id})
        assert retry.status_code == 422
        async with maker() as session:
            messages = (
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
            assert [m.role for m in messages] == ["user", "assistant"]
            assert messages[-1].inline_value == "Hello world"
    finally:
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_mutations_conflict_with_generation_and_reconnect_is_clean(
    user_id, tables, tmp_path, monkeypatch
):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    slow = SlowPipeline()
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda: slow)
    maker = db.get_session_manager().async_session_maker
    service = ChattingService()
    file_id = await _upload(maker, user_id, "a.txt", "data", store)
    other_id = await _upload(maker, user_id, "b.txt", "data", store)
    async with maker() as session:
        thread = Thread(id=uuid.uuid4().hex, user_id=user_id, title="t")
        session.add(thread)
        await session.commit()
        thread_id = thread.id
    # Link while idle so the delete path has a generating linked thread.
    async with maker() as session:
        from services.file import link_file_with_thread

        await link_file_with_thread(
            session, user_id=user_id, file_id=file_id, thread_id=thread_id
        )
    async with maker() as session:
        run = await service.start_generation(session, thread_id, user_id, "slow")
    http = await _client(user_id, slow, monkeypatch)
    try:
        attach = await http.post(f"/api/files/{other_id}/link/thread/{thread_id}")
        assert attach.status_code == 409
        unlink = await http.delete(f"/api/files/{file_id}/link/thread/{thread_id}")
        assert unlink.status_code == 409
        delete = await http.delete(f"/api/files/{file_id}")
        assert delete.status_code == 409
        # Reconnect replays without creating links or messages.
        tail = await http.get(f"/api/chat/stream/{thread_id}?offset=0")
        assert tail.status_code == 200
    finally:
        run.cancel()
        await run.wait_done()
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)
    async with maker() as session:
        assert await get_thread_link(session, file_id, thread_id) is not None
        assert await get_thread_link(session, other_id, thread_id) is None


async def test_thread_files_list_and_idempotent_unlink(user_id, tables, tmp_path, monkeypatch):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    fake = FakePipeline()
    http = await _client(user_id, fake, monkeypatch)
    try:
        maker = db.get_session_manager().async_session_maker
        file_id = await _upload(maker, user_id, "a.txt", "data", store)
        first = await http.post("/api/chat/stream", json={"message": "Hi"})
        thread_id = first.headers["x-clyre-thread-id"]
        run = get_run(thread_id)
        assert run is not None
        await run.wait_done()
        listed = await http.get(f"/api/thread/{thread_id}/files")
        assert listed.status_code == 200
        assert listed.json() == []
        # Link then list shows the file; unlink twice stays 204.
        link = await http.post(f"/api/files/{file_id}/link/thread/{thread_id}")
        assert link.status_code == 200
        listed = await http.get(f"/api/thread/{thread_id}/files")
        assert [f["id"] for f in listed.json()] == [file_id]
        assert (
            await http.delete(f"/api/files/{file_id}/link/thread/{thread_id}")
        ).status_code == 204
        assert (
            await http.delete(f"/api/files/{file_id}/link/thread/{thread_id}")
        ).status_code == 204
        # Foreign thread stays 404.
        assert (await http.get(f"/api/thread/{uuid.uuid4().hex}/files")).status_code == 404
    finally:
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_standalone_link_respects_attachment_limit(
    user_id, tables, tmp_path, monkeypatch
):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    monkeypatch.setattr(file_module.env, "MAX_THREAD_ATTACHMENTS", 2)
    fake = FakePipeline()
    http = await _client(user_id, fake, monkeypatch)
    try:
        maker = db.get_session_manager().async_session_maker
        file_ids = [await _upload(maker, user_id, f"f{i}.txt", "data", store) for i in range(3)]
        first = await http.post("/api/chat/stream", json={"message": "Hi"})
        thread_id = first.headers["x-clyre-thread-id"]
        run = get_run(thread_id)
        assert run is not None
        await run.wait_done()

        assert (
            await http.post(f"/api/files/{file_ids[0]}/link/thread/{thread_id}")
        ).status_code == 200
        assert (
            await http.post(f"/api/files/{file_ids[1]}/link/thread/{thread_id}")
        ).status_code == 200
        # Re-attaching an existing relationship remains an idempotent success.
        assert (
            await http.post(f"/api/files/{file_ids[0]}/link/thread/{thread_id}")
        ).status_code == 200
        overflow = await http.post(f"/api/files/{file_ids[2]}/link/thread/{thread_id}")
        assert overflow.status_code == 409
        assert "limit is 2" in overflow.json()["detail"]
    finally:
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_foreign_file_and_thread_return_404_before_idle_check(
    user_id, tables, tmp_path, monkeypatch
):
    store = LocalFileStore(tmp_path / "files")
    monkeypatch.setattr(file_module, "get_file_store", lambda: store)
    monkeypatch.setattr("services.chat_context.get_file_store", lambda: store)
    slow = SlowPipeline()
    http = await _client(user_id, slow, monkeypatch)
    run = None
    try:
        maker = db.get_session_manager().async_session_maker
        async with maker() as session:
            stranger = User()
            session.add(stranger)
            await session.flush()
            stranger_thread = Thread(id=uuid.uuid4().hex, user_id=stranger.id, title="foreign")
            session.add(stranger_thread)
            await session.commit()
            stranger_id = stranger.id
            stranger_thread_id = stranger_thread.id

        own_file = await _upload(maker, user_id, "own.txt", "data", store)
        foreign_file = await _upload(maker, stranger_id, "foreign.txt", "secret", store)
        async with maker() as session:
            from services.file import link_file_with_thread

            await link_file_with_thread(
                session,
                user_id=stranger_id,
                file_id=foreign_file,
                thread_id=stranger_thread_id,
            )
            run = await ChattingService().start_generation(
                session, stranger_thread_id, stranger_id, "slow"
            )

        attach = await http.post(f"/api/files/{own_file}/link/thread/{stranger_thread_id}")
        assert attach.status_code == 404

        delete = await http.delete(f"/api/files/{foreign_file}")
        assert delete.status_code == 404
    finally:
        if run is not None:
            run.cancel()
            await run.wait_done()
        await http.aclose()
        app.dependency_overrides.pop(web.extract_access_token, None)


async def test_start_registers_nothing_when_commit_fails(user_id, tables, monkeypatch):
    fake = FakePipeline()
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda: fake)
    maker = db.get_session_manager().async_session_maker
    service = ChattingService()
    calls = {"n": 0}

    async with maker() as session:

        async def _flaky_commit():
            calls["n"] += 1
            raise RuntimeError("db down")

        monkeypatch.setattr(session, "commit", _flaky_commit)
        with pytest.raises(RuntimeError):
            await service.start_generation(session, None, user_id, "hi")
        await session.rollback()
    assert calls["n"] == 1
    async with maker() as session:
        assert await session.scalar(select(func.count(Thread.id))) == 0


async def test_concurrent_starts_still_single_winner(user_id, tables, monkeypatch):
    gate = asyncio.Event()

    class GatedPipeline(FakePipeline):
        async def chat_completion_stream(self, history, **kwargs):
            self.calls.append({"history": list(history), **kwargs})
            await gate.wait()
            for chunk in self._chunks:
                yield ("content", chunk)

    fake = GatedPipeline()
    monkeypatch.setattr(chatting_module, "get_inference_pipeline", lambda: fake)
    maker = db.get_session_manager().async_session_maker
    async with maker() as session:
        thread = Thread(id=uuid.uuid4().hex, user_id=user_id, title="t")
        session.add(thread)
        await session.commit()
        thread_id = thread.id
    service = ChattingService()

    async def _send(message):
        async with maker() as session:
            return await service.start_generation(session, thread_id, user_id, message)

    winner, loser = await asyncio.gather(
        _send("first"), _send("second"), return_exceptions=True
    )
    from services.generation import GenerationRun as Run

    assert isinstance(winner, Run) or isinstance(loser, Run)
    conflicts = [r for r in (winner, loser) if isinstance(r, GenerationConflict)]
    assert len(conflicts) == 1
    gate.set()
    run = winner if isinstance(winner, Run) else loser
    assert isinstance(run, Run)
    await run.wait_done()
