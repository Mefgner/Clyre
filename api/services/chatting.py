import asyncio
import logging
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from crud import (
    create_generation_run,
    create_message,
    create_thread,
    finish_generation_run,
    get_messages_in_thread,
    get_running_run_for_thread,
    get_thread_by_id,
    update_thread_time,
)
from crud.message import (
    get_last_message_order_in_thread,
    reserve_assistant_message,
    update_message_content,
)
from db import get_session_manager
from models import GenerationRunRow, Message, Thread
from pipelines.inference import Tier, get_inference_pipeline
from schemas.chatting import StreamingBlock
from services.generation import (
    PARTIAL_FLUSH_SECONDS,
    GenerationConflict,
    GenerationRun,
    GenerationStatus,
    get_run,
    register_run,
    schedule_eviction,
)
from utils import timing

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

# Serializes generation starts process-wide: the active-run check, the
# user-message save (incl. the title call) and run registration must be one
# atomic section — two concurrent sends on a thread would otherwise both pass
# the check and the second registration orphans the first run.
_generation_start_lock = asyncio.Lock()


class ChattingService:
    # Raw inline LLM call. Should be replaced by a dedicated functional node
    # (e.g. a title-generation step in the pipeline layer), not kept here.
    @staticmethod
    async def generate_thread_title(message: str) -> str:
        llama = get_inference_pipeline(Tier.SMALL)
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
        llama = get_inference_pipeline(Tier.SMALL)
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

    async def start_generation(
        self,
        session: AsyncSession,
        thread_id: str | None,
        user_id: str,
        message: str,
        enable_thinking: bool | None = None,
    ) -> GenerationRun:
        if thread_id is not None:
            await self._ensure_owned_thread(session, thread_id, user_id)

        async with _generation_start_lock:
            if thread_id is not None:
                await self._ensure_no_active(session, thread_id)

            _, thread_id = await self.save_message(
                session,
                user_id,
                message,
                "user",
                thread_id,
            )

            await session.commit()

            Logger.debug("User message saved for thread_id: %s", thread_id)

            return await self._launch(session, thread_id, user_id, enable_thinking)

    async def retry_generation(
        self,
        session: AsyncSession,
        thread_id: str,
        user_id: str,
        enable_thinking: bool | None = None,
    ) -> GenerationRun:
        """Regenerate the trailing assistant message in place (retry policy in PLAN 2.7)."""
        await self._ensure_owned_thread(session, thread_id, user_id)

        async with _generation_start_lock:
            await self._ensure_no_active(session, thread_id)

            thread = await get_thread_by_id(session, thread_id, user_id)
            if not thread:
                raise ValueError("Thread not found")

            messages = list(thread.messages)
            if not messages or messages[-1].role != "assistant":
                raise GenerationConflict("Nothing to retry")

            order = messages[-1].order
            await session.delete(messages[-1])
            await session.commit()
            Logger.info(
                "Retry: deleted trailing assistant message thread=%s order=%d",
                thread_id,
                order,
            )

            return await self._launch(
                session, thread_id, user_id, enable_thinking, forced_order=order
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
        llama = get_inference_pipeline(Tier.SMALL)

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

        async def emit_terminal() -> None:
            await run.publish(
                StreamingBlock(
                    chunk=None, event="assistant_message_insert", thread_id=thread_id
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
                await emit_terminal()
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
