import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from crud import (
    create_generation_run,
    create_message,
    create_thread,
    finish_generation_run,
    get_messages_in_thread,
    get_running_run_for_thread,
    get_thread_by_id,
    link_file_to_thread,
    list_thread_files,
    update_thread_time,
)
from crud.message import (
    get_last_message_order_in_thread,
    reserve_assistant_message,
    update_message_content,
)
from db import get_session_manager
from models import GenerationRunRow, Message, Thread
from pipelines.inference import get_inference_pipeline
from schemas.chatting import ContextWindowBlock, StreamingBlock
from services.chat_context import AttachedFile, AttachmentLimitExceeded, prepare_attached_files
from services.context_window import ContextWindow, select_context_window
from services.generation import (
    PARTIAL_FLUSH_SECONDS,
    GenerationConflict,
    GenerationRun,
    GenerationStatus,
    get_generation_mutex,
    get_run,
    register_run,
    schedule_eviction,
)
from utils import env, timing

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.DEBUG)

# Injected at a stable position (first entry of the history) on every request.
DEFAULT_SYSTEM_PROMPT = (
    "You are Clyre, a locally-running assistant for a small team or household.\n"
    "Respond in the language of the user's message.\n"
    "Be direct and factual. If you are not sure, say so honestly instead of guessing.\n"
    "You have no access to external tools, files, or the internet unless explicitly "
    "stated otherwise — never invent files, sources, or data.\n"
    "Format answers with Markdown."
)


@dataclass(slots=True)
class _PreparedStart:
    is_new: bool
    thread: Thread | None
    title: str | None
    prompt: list[dict[str, str]]
    attached: list[AttachedFile]
    union_ids: list[str]
    existing_ids: list[str]
    persisted: list[Message]
    prompt_tokens: int
    context_window: ContextWindow


@dataclass(slots=True)
class _PreparedRetry:
    thread: Thread
    prompt: list[dict[str, str]]
    attached: list[AttachedFile]
    union_ids: list[str]
    victim_order: int
    prompt_tokens: int
    context_window: ContextWindow


def _dedupe_ids(file_ids: Iterable[str] | None) -> list[str]:
    if not file_ids:
        return []
    return list(dict.fromkeys(fid for fid in file_ids if fid))


def _attachment_limit() -> int:
    limit = int(env.MAX_THREAD_ATTACHMENTS)
    if limit <= 0:
        raise RuntimeError("MAX_THREAD_ATTACHMENTS must be positive")
    return limit


class ChattingService:
    # Raw inline LLM call. Should be replaced by a dedicated functional node
    # (e.g. a title-generation step in the pipeline layer), not kept here.
    @staticmethod
    async def generate_thread_title(message: str) -> str:
        llama = get_inference_pipeline()
        llama_prompt = f"Create a concise and descriptive title for the given message (min. 4 words and up to 6 words (strict), use language of context given below):\n\n{message}\n\nTitle:"
        response_data = await llama.chat_completion_sync(
            [{"role": "user", "content": llama_prompt}],
            enable_thinking=False,
        )
        return response_data["choices"][0]["message"]["content"][:90].strip().strip('"')

    async def save_message(
        self,
        session: AsyncSession,
        user_id: str,
        message: str,
        role: str,
        thread_id: str | None = None,
        thinking: str | None = None,
    ) -> tuple[str, str]:
        thread: Thread | None = None

        current_thread_id: str = thread_id or ""

        if not current_thread_id:
            thread = await create_thread(
                session, user_id=user_id, title=await self.generate_thread_title(message)
            )
            current_thread_id = thread.id
            last_order = -1
        else:
            last_order = await get_last_message_order_in_thread(
                session, thread_id=current_thread_id, user_id=user_id
            )

        if not thread:
            thread = await get_thread_by_id(session, current_thread_id, user_id)

        if not thread:
            raise ValueError("Thread not found")

        await update_thread_time(session, thread, timing.get_utc_now())

        await session.commit()

        new_message = await create_message(
            session,
            user_id=user_id,
            thread_id=current_thread_id,
            role=role,
            content=message,
            order=last_order + 1,
            thinking=thinking,
        )
        return new_message.id, current_thread_id

    @staticmethod
    def build_history(messages: Iterable[Message]) -> list[dict[str, str]]:
        # Thinking blocks are intentionally never re-sent to the model (Qwen3.5
        # model card: no thinking content in history). If a preserve-thinking
        # model is ever added, it will likely need its own context-building
        # function instead of extending this one.
        history = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        for msg in messages:
            if msg.role == "system":
                continue
            if msg.role == "assistant" and msg.inline_value is None:
                # Reserved row never written by its run (crash before the
                # first flush) — sending it would hand the model a null turn.
                continue
            history.append({"role": msg.role, "content": msg.inline_value or ""})
        return history

    # Legacy non-streaming path. Do not use for new code; kept only as a
    # fallback and a likely candidate for removal.
    async def generate_llm_response(
        self, session: AsyncSession, thread_id: str, user_id: str
    ) -> tuple[Message, str]:
        llama = get_inference_pipeline()
        messages = await get_messages_in_thread(session, thread_id, user_id)
        if not messages:
            raise ValueError("Message not found")

        thread = await get_thread_by_id(session, thread_id, user_id)

        if not thread:
            raise ValueError("Thread not found")

        await update_thread_time(session, thread, timing.get_utc_now())

        history = self.build_history(messages)
        response_data = await llama.chat_completion_sync(history)
        response_message = await create_message(
            session,
            user_id=user_id,
            thread_id=thread_id,
            role="assistant",
            content=response_data["choices"][0]["message"]["content"],
            order=await get_last_message_order_in_thread(session, thread_id, user_id) + 1,
        )

        await session.commit()

        return response_message, thread_id

    async def _ensure_no_active(self, session: AsyncSession, thread_id: str) -> None:
        existing = get_run(thread_id)
        if existing is not None and not existing.done:
            Logger.warning(
                "Generation conflict (registry) thread=%s run=%s status=%s",
                thread_id,
                existing.journal_id,
                existing.status.value,
            )
            raise GenerationConflict("Generation already active for this thread")
        if await get_running_run_for_thread(session, thread_id) is not None:
            Logger.warning("Generation conflict (journal) thread=%s", thread_id)
            raise GenerationConflict("Generation already active for this thread")

    @staticmethod
    async def _ensure_owned_thread(session: AsyncSession, thread_id: str, user_id: str) -> None:
        # Ownership before activity: a foreign thread id must fail with
        # "not found" instead of leaking generation state via 409-vs-404.
        thread = await get_thread_by_id(session, thread_id, user_id)
        if not thread:
            raise ValueError("Thread not found")

    async def _prepare_start(
        self,
        session: AsyncSession,
        thread_id: str | None,
        user_id: str,
        message: str,
        file_ids: list[str],
        enable_thinking: bool | None,
    ) -> _PreparedStart:
        new_ids = _dedupe_ids(file_ids)
        if thread_id is not None:
            await self._ensure_owned_thread(session, thread_id, user_id)
            await self._ensure_no_active(session, thread_id)
            thread = await get_thread_by_id(session, thread_id, user_id)
            if not thread:
                raise ValueError("Thread not found")
            persisted = list(await get_messages_in_thread(session, thread_id, user_id))
            existing_rows = await list_thread_files(session, thread_id, user_id)
            existing_ids = [row.id for row in existing_rows]
        else:
            thread = None
            persisted = []
            existing_ids = []

        union_ids = list(dict.fromkeys([*existing_ids, *new_ids]))
        limit = _attachment_limit()
        if len(union_ids) > limit:
            raise AttachmentLimitExceeded(len(union_ids), limit)

        attached = await prepare_attached_files(session, user_id, union_ids)

        # Transient current message: budget is verified before any row exists,
        # so a failed preflight creates no thread, messages, journal, or links.
        transient = Message(
            role="user",
            inline_value=message,
            thinking_value=None,
            hash="",
            user_id=user_id,
            thread_id=thread_id or "",
            order=(persisted[-1].order + 1) if persisted else 0,
        )
        context_window = await select_context_window(
            persisted,
            transient,
            attached,
            base_prompt=DEFAULT_SYSTEM_PROMPT,
            inference=get_inference_pipeline(),
            enable_thinking=enable_thinking,
        )

        title: str | None = None
        if thread is None:
            title = await self.generate_thread_title(message)
        return _PreparedStart(
            is_new=thread is None,
            thread=thread,
            title=title,
            prompt=context_window.prompt,
            attached=attached,
            union_ids=union_ids,
            existing_ids=existing_ids,
            persisted=persisted,
            prompt_tokens=context_window.prompt_tokens,
            context_window=context_window,
        )

    async def _prepare_retry(
        self,
        session: AsyncSession,
        thread_id: str,
        user_id: str,
        enable_thinking: bool | None,
    ) -> _PreparedRetry:
        await self._ensure_owned_thread(session, thread_id, user_id)
        await self._ensure_no_active(session, thread_id)

        thread = await get_thread_by_id(session, thread_id, user_id)
        if not thread:
            raise ValueError("Thread not found")

        messages = list(thread.messages)
        if not messages or messages[-1].role != "assistant":
            raise GenerationConflict("Nothing to retry")

        victim_order = messages[-1].order
        # The victim is the trailing assistant; the preceding user message is
        # the current request and earlier messages are selectable history.
        kept = messages[:-1]
        if not kept or kept[-1].role != "user":
            raise GenerationConflict("Nothing to retry")
        current = kept[-1]
        history = kept[:-1]

        existing_rows = await list_thread_files(session, thread_id, user_id)
        union_ids = [row.id for row in existing_rows]
        limit = _attachment_limit()
        if len(union_ids) > limit:  # pragma: no cover - defensive; links were capped
            raise AttachmentLimitExceeded(len(union_ids), limit)
        attached = await prepare_attached_files(session, user_id, union_ids)
        context_window = await select_context_window(
            history,
            current,
            attached,
            base_prompt=DEFAULT_SYSTEM_PROMPT,
            inference=get_inference_pipeline(),
            enable_thinking=enable_thinking,
        )
        return _PreparedRetry(
            thread=thread,
            prompt=context_window.prompt,
            attached=attached,
            union_ids=union_ids,
            victim_order=victim_order,
            prompt_tokens=context_window.prompt_tokens,
            context_window=context_window,
        )

    async def start_generation(
        self,
        session: AsyncSession,
        thread_id: str | None,
        user_id: str,
        message: str,
        enable_thinking: bool | None = None,
        file_ids: list[str] | None = None,
    ) -> GenerationRun:
        if thread_id is not None:
            await self._ensure_owned_thread(session, thread_id, user_id)

        async with get_generation_mutex():
            # _prepare_start repeats the ownership + activity checks under the
            # same lock as the file batch validation and the commit.
            try:
                prepared = await self._prepare_start(
                    session,
                    thread_id,
                    user_id,
                    message,
                    _dedupe_ids(file_ids),
                    enable_thinking,
                )
            except Exception:
                await session.rollback()
                raise

            try:
                if prepared.is_new:
                    thread_row = await create_thread(
                        session, user_id=user_id, title=prepared.title or "New Thread"
                    )
                    # Flush the header first: GenerationRunRow has no ORM
                    # relationship to Thread, so the unit of work cannot order
                    # the inserts itself (flush, not commit — atomicity stays).
                    await session.flush()
                    resolved_thread_id = thread_row.id
                    last_order = -1
                else:
                    assert prepared.thread is not None
                    thread_row = prepared.thread
                    resolved_thread_id = thread_row.id
                    last_order = prepared.persisted[-1].order if prepared.persisted else -1

                # Link only genuinely new ids; re-attach is a no-op by id.
                already = set(prepared.existing_ids)
                for fid in prepared.union_ids:
                    if fid not in already:
                        await link_file_to_thread(session, fid, resolved_thread_id)

                await create_message(
                    session,
                    user_id=user_id,
                    thread_id=resolved_thread_id,
                    role="user",
                    content=message,
                    order=last_order + 1,
                )
                await update_thread_time(session, thread_row, timing.get_utc_now())
                journal_row = await create_generation_run(session, resolved_thread_id, user_id)
                reserved = await reserve_assistant_message(
                    session,
                    user_id=user_id,
                    thread_id=resolved_thread_id,
                    order=last_order + 2,
                )
                await session.commit()
            except Exception:
                # A failed commit must not leave a partially accepted start:
                # no run is registered and no background task is launched.
                await session.rollback()
                raise

            Logger.debug(
                "User message saved for thread_id: %s (files=%d prompt_tokens=%d)",
                resolved_thread_id,
                len(prepared.attached),
                prepared.prompt_tokens,
            )

            return await self._launch_with_prompt(
                session,
                resolved_thread_id,
                user_id,
                enable_thinking,
                prepared.prompt,
                prepared.context_window,
                journal_row.id,
                reserved.id,
            )

    async def retry_generation(
        self,
        session: AsyncSession,
        thread_id: str,
        user_id: str,
        enable_thinking: bool | None = None,
    ) -> GenerationRun:
        """Regenerate the trailing assistant message in place (retry policy in PLAN 2.7)."""
        await self._ensure_owned_thread(session, thread_id, user_id)

        async with get_generation_mutex():
            try:
                prepared = await self._prepare_retry(
                    session, thread_id, user_id, enable_thinking
                )
            except Exception:
                await session.rollback()
                raise

            try:
                # Delete the failed answer and reserve its replacement in one
                # transaction: an unsuccessful retry keeps the previous answer.
                victim = None
                for msg in prepared.thread.messages:
                    if msg.role == "assistant" and msg.order == prepared.victim_order:
                        victim = msg
                        break
                if victim is None:
                    raise GenerationConflict("Nothing to retry")
                await session.delete(victim)
                await session.flush()
                Logger.info(
                    "Retry: deleted trailing assistant message thread=%s order=%d",
                    thread_id,
                    prepared.victim_order,
                )
                journal_row = await create_generation_run(session, thread_id, user_id)
                reserved = await reserve_assistant_message(
                    session,
                    user_id=user_id,
                    thread_id=thread_id,
                    order=prepared.victim_order,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

            return await self._launch_with_prompt(
                session,
                thread_id,
                user_id,
                enable_thinking,
                prepared.prompt,
                prepared.context_window,
                journal_row.id,
                reserved.id,
            )

    @staticmethod
    def stop_generation(thread_id: str) -> bool:
        run = get_run(thread_id)
        if run is None or run.done:
            Logger.info("Stop ignored: no active generation thread=%s", thread_id)
            return False
        Logger.info(
            "Stopping generation thread=%s run=%s (response so far: %d chars)",
            thread_id,
            run.journal_id,
            len(run.response),
        )
        return run.request_stop()

    async def _launch(
        self,
        session: AsyncSession,
        thread_id: str,
        user_id: str,
        enable_thinking: bool | None = None,
        forced_order: int | None = None,
    ) -> GenerationRun:
        thread = await get_thread_by_id(session, thread_id, user_id)

        if not thread:
            raise ValueError("Thread not found")

        # Fresh query on purpose: a retried run must not see a just-deleted
        # partial answer lingering in the identity map's relationship cache.
        history = self.build_history(await get_messages_in_thread(session, thread_id, user_id))
        llama = get_inference_pipeline()

        if forced_order is not None:
            order = forced_order
        else:
            order = await get_last_message_order_in_thread(session, thread_id, user_id) + 1

        journal_row = await create_generation_run(session, thread_id, user_id)
        reserved = await reserve_assistant_message(
            session,
            user_id=user_id,
            thread_id=thread_id,
            order=order,
        )
        reserved_id = reserved.id
        await session.commit()

        run = GenerationRun(thread_id, journal_row.id)
        register_run(run)
        Logger.info(
            "Generation starting thread=%s user=%s run=%s order=%d thinking=%s history=%d",
            thread_id,
            user_id,
            journal_row.id,
            order,
            bool(enable_thinking),
            len(history),
        )

        async def _load_reserved(fresh_session: AsyncSession) -> Message | None:
            return await fresh_session.get(Message, reserved_id)

        async def flush_partial(force: bool = False) -> None:
            now = asyncio.get_running_loop().time()
            if not force and now - run.last_flush < PARTIAL_FLUSH_SECONDS:
                return
            run.last_flush = now
            try:
                async with get_session_manager().async_session_maker() as fresh_session:
                    message = await _load_reserved(fresh_session)
                    if message is not None:
                        await update_message_content(
                            fresh_session, message, run.response, run.thinking or None
                        )
                        await fresh_session.commit()
            except Exception:
                # A failed partial flush must never kill the generation itself;
                # finalize_journal retries the write at the terminal state.
                Logger.exception(
                    "Partial flush failed thread=%s run=%s", thread_id, run.journal_id
                )

        async def finalize_journal(status: GenerationStatus) -> None:
            async with get_session_manager().async_session_maker() as fresh_session:
                message = await _load_reserved(fresh_session)
                if message is not None:
                    if run.response == "" and run.thinking == "":
                        await fresh_session.delete(message)
                    else:
                        await update_message_content(
                            fresh_session, message, run.response, run.thinking or None
                        )
                row = await fresh_session.get(GenerationRunRow, run.journal_id)
                if row is not None:
                    await finish_generation_run(fresh_session, row, status.value)
                await fresh_session.commit()

        async def emit_terminal(error_message: str | None = None) -> None:
            await run.publish(
                StreamingBlock(
                    chunk=None, event="assistant_message_insert", thread_id=thread_id
                ).model_dump_json(by_alias=True)
                + "\n"
            )
            if error_message is not None:
                await run.publish(
                    StreamingBlock(
                        chunk=error_message, event="error", thread_id=thread_id
                    ).model_dump_json(by_alias=True)
                    + "\n"
                )
            await run.publish(
                StreamingBlock(chunk=None, event="done").model_dump_json(by_alias=True) + "\n"
            )

        async def execute() -> None:
            loop = asyncio.get_running_loop()
            started_at = loop.time()
            first_token_at: float | None = None
            content_chunks = 0
            thinking_chunks = 0
            status = GenerationStatus.FINISHED
            try:
                await run.publish(
                    StreamingBlock(
                        chunk=None, event="user_message_insert", thread_id=thread_id
                    ).model_dump_json(by_alias=True)
                    + "\n"
                )

                async for kind, text in llama.chat_completion_stream(
                    history, enable_thinking=enable_thinking
                ):
                    if first_token_at is None:
                        first_token_at = loop.time()
                        Logger.info(
                            "First token thread=%s run=%s after %.3fs",
                            thread_id,
                            run.journal_id,
                            first_token_at - started_at,
                        )

                    if kind == "thinking":
                        event = "new_thinking_chunk"
                        run.thinking += text
                        thinking_chunks += 1
                    else:
                        event = "new_chunk"
                        run.response += text
                        content_chunks += 1

                    await run.publish(
                        StreamingBlock(chunk=text, event=event).model_dump_json(by_alias=True)
                        + "\n"
                    )
                    await flush_partial()

                Logger.debug("Generation completed for thread_id: %s", thread_id)

                await flush_partial(force=True)
                await emit_terminal()
            except asyncio.CancelledError:
                status = GenerationStatus.STOPPED
                await flush_partial(force=True)
                await emit_terminal()
                Logger.warning(
                    "Generation cancelled thread=%s run=%s after %.3fs (%d content / %d "
                    "thinking chunks, response=%d chars)",
                    thread_id,
                    run.journal_id,
                    loop.time() - started_at,
                    content_chunks,
                    thinking_chunks,
                    len(run.response),
                )
            except Exception:
                status = GenerationStatus.FAILED
                Logger.exception(
                    "Generation failed thread=%s run=%s after %.3fs (%d content / %d "
                    "thinking chunks, response=%d chars, thinking=%d chars)",
                    thread_id,
                    run.journal_id,
                    loop.time() - started_at,
                    content_chunks,
                    thinking_chunks,
                    len(run.response),
                    len(run.thinking),
                )
                await flush_partial(force=True)
                await emit_terminal("Generation failed. Please try again.")
            finally:
                # A failed journal write must never wedge the run: skipping
                # finish() hangs every subscriber and 409-locks the thread
                # until process restart. Finalize is best-effort; the terminal
                # transition itself is mandatory.
                try:
                    await finalize_journal(status)
                except Exception:
                    Logger.exception(
                        "Journal finalize failed thread=%s run=%s status=%s",
                        thread_id,
                        run.journal_id,
                        status.value,
                    )
                await run.finish(status)
                schedule_eviction(run)
                Logger.info(
                    "Generation terminal thread=%s run=%s status=%s duration=%.3fs "
                    "first_token=%.3fs content_chunks=%d thinking_chunks=%d "
                    "response_chars=%d thinking_chars=%d",
                    thread_id,
                    run.journal_id,
                    status.value,
                    loop.time() - started_at,
                    (first_token_at - started_at) if first_token_at is not None else -1.0,
                    content_chunks,
                    thinking_chunks,
                    len(run.response),
                    len(run.thinking),
                )

        run.attach_task(asyncio.create_task(execute()))
        return run

    async def _launch_with_prompt(
        self,
        session: AsyncSession,
        thread_id: str,
        user_id: str,
        enable_thinking: bool | None,
        history: list[dict[str, str]],
        context_window: ContextWindow,
        journal_id: str,
        reserved_id: str,
    ) -> GenerationRun:
        """Register and run background generation for an already-committed start."""
        _ = session  # commit happened in the caller; background uses fresh sessions.
        llama = get_inference_pipeline()

        run = GenerationRun(thread_id, journal_id)
        register_run(run)
        Logger.info(
            "Generation starting thread=%s user=%s run=%s thinking=%s history=%d",
            thread_id,
            user_id,
            journal_id,
            bool(enable_thinking),
            len(history),
        )

        async def _load_reserved(fresh_session: AsyncSession) -> Message | None:
            return await fresh_session.get(Message, reserved_id)

        async def flush_partial(force: bool = False) -> None:
            now = asyncio.get_running_loop().time()
            if not force and now - run.last_flush < PARTIAL_FLUSH_SECONDS:
                return
            run.last_flush = now
            try:
                async with get_session_manager().async_session_maker() as fresh_session:
                    message = await _load_reserved(fresh_session)
                    if message is not None:
                        await update_message_content(
                            fresh_session, message, run.response, run.thinking or None
                        )
                        await fresh_session.commit()
            except Exception:
                Logger.exception(
                    "Partial flush failed thread=%s run=%s", thread_id, run.journal_id
                )

        async def finalize_journal(status: GenerationStatus) -> None:
            async with get_session_manager().async_session_maker() as fresh_session:
                message = await _load_reserved(fresh_session)
                if message is not None:
                    if run.response == "" and run.thinking == "":
                        await fresh_session.delete(message)
                    else:
                        await update_message_content(
                            fresh_session, message, run.response, run.thinking or None
                        )
                row = await fresh_session.get(GenerationRunRow, run.journal_id)
                if row is not None:
                    await finish_generation_run(fresh_session, row, status.value)
                await fresh_session.commit()

        async def emit_terminal(error_message: str | None = None) -> None:
            await run.publish(
                StreamingBlock(
                    chunk=None, event="assistant_message_insert", thread_id=thread_id
                ).model_dump_json(by_alias=True)
                + "\n"
            )
            if error_message is not None:
                await run.publish(
                    StreamingBlock(
                        chunk=error_message, event="error", thread_id=thread_id
                    ).model_dump_json(by_alias=True)
                    + "\n"
                )
            await run.publish(
                StreamingBlock(chunk=None, event="done").model_dump_json(by_alias=True) + "\n"
            )

        async def execute() -> None:
            loop = asyncio.get_running_loop()
            started_at = loop.time()
            first_token_at: float | None = None
            content_chunks = 0
            thinking_chunks = 0
            status = GenerationStatus.FINISHED
            try:
                await run.publish(
                    StreamingBlock(
                        chunk=None, event="user_message_insert", thread_id=thread_id
                    ).model_dump_json(by_alias=True)
                    + "\n"
                )
                if context_window.measured_exactly:
                    await run.publish(
                        ContextWindowBlock(
                            thread_id=thread_id,
                            included_messages=context_window.included_messages,
                            omitted_messages=context_window.omitted_messages,
                            first_included_order=context_window.first_included_order,
                            prompt_tokens=context_window.prompt_tokens,
                            slot_tokens=context_window.slot_tokens,
                            reserved_output_tokens=context_window.reserved_output_tokens,
                        ).model_dump_json(by_alias=True)
                        + "\n"
                    )

                async for kind, text in llama.chat_completion_stream(
                    history, enable_thinking=enable_thinking
                ):
                    if first_token_at is None:
                        first_token_at = loop.time()
                        Logger.info(
                            "First token thread=%s run=%s after %.3fs",
                            thread_id,
                            run.journal_id,
                            first_token_at - started_at,
                        )

                    if kind == "thinking":
                        event = "new_thinking_chunk"
                        run.thinking += text
                        thinking_chunks += 1
                    else:
                        event = "new_chunk"
                        run.response += text
                        content_chunks += 1

                    await run.publish(
                        StreamingBlock(chunk=text, event=event).model_dump_json(by_alias=True)
                        + "\n"
                    )
                    await flush_partial()

                Logger.debug("Generation completed for thread_id: %s", thread_id)

                await flush_partial(force=True)
                await emit_terminal()
            except asyncio.CancelledError:
                status = GenerationStatus.STOPPED
                await flush_partial(force=True)
                await emit_terminal()
                Logger.warning(
                    "Generation cancelled thread=%s run=%s after %.3fs (%d content / %d "
                    "thinking chunks, response=%d chars)",
                    thread_id,
                    run.journal_id,
                    loop.time() - started_at,
                    content_chunks,
                    thinking_chunks,
                    len(run.response),
                )
            except Exception:
                status = GenerationStatus.FAILED
                Logger.exception(
                    "Generation failed thread=%s run=%s after %.3fs (%d content / %d "
                    "thinking chunks, response=%d chars, thinking=%d chars)",
                    thread_id,
                    run.journal_id,
                    loop.time() - started_at,
                    content_chunks,
                    thinking_chunks,
                    len(run.response),
                    len(run.thinking),
                )
                await flush_partial(force=True)
                await emit_terminal("Generation failed. Please try again.")
            finally:
                try:
                    await finalize_journal(status)
                except Exception:
                    Logger.exception(
                        "Journal finalize failed thread=%s run=%s status=%s",
                        thread_id,
                        run.journal_id,
                        status.value,
                    )
                await run.finish(status)
                schedule_eviction(run)
                Logger.info(
                    "Generation terminal thread=%s run=%s status=%s duration=%.3fs "
                    "first_token=%.3fs content_chunks=%d thinking_chunks=%d "
                    "response_chars=%d thinking_chars=%d",
                    thread_id,
                    run.journal_id,
                    status.value,
                    loop.time() - started_at,
                    (first_token_at - started_at) if first_token_at is not None else -1.0,
                    content_chunks,
                    thinking_chunks,
                    len(run.response),
                    len(run.thinking),
                )

        run.attach_task(asyncio.create_task(execute()))
        return run
