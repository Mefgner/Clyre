import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from crud import (
    create_message,
    create_thread,
    get_messages_in_thread,
    get_thread_by_id,
    update_thread_time,
)
from crud.message import get_last_message_order_in_thread
from models import Message, Thread
from pipelines.llama import get_llama_pipeline
from schemas.chatting import StreamingBlock
from utils import timing

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.DEBUG)


class ChattingService:
    @staticmethod
    async def generate_thread_title(message: str) -> str:
        llama = get_llama_pipeline("")
        llama_prompt = f"Create a concise and descriptive title for the given message (min. 4 words and up to 6 words (strict), use language of context given below):\n\n{message}\n\nTitle:"
        response_data = await llama.chat_completion_sync(
            [{"role": "user", "content": llama_prompt}],
        )
        return response_data["choices"][0]["message"]["content"][:90].strip().strip('"')

    async def save_message(
        self,
        session: AsyncSession,
        user_id: str,
        message: str,
        role: str,
        thread_id: str | None = None,
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
        )
        return new_message.id, current_thread_id

    @staticmethod
    def build_history(messages: Iterable[Message]) -> list[dict[str, str]]:
        history = []
        for msg in messages:
            history.append({"role": msg.role, "content": msg.inline_value})
        return history

    async def generate_llm_response(
        self, session: AsyncSession, thread_id: str, user_id: str, model: str = ""
    ) -> tuple[Message, str]:
        llama = get_llama_pipeline(model)
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

    async def stream_response(
        self,
        session: AsyncSession,
        thread_id: str,
        user_id: str,
        message: str,
        get_stop_signal: Callable[[], Awaitable[bool]],
        model: str = "",
    ):
        _, thread_id = await self.save_message(
            session,
            user_id,
            message,
            "user",
            thread_id,
        )

        await session.commit()

        Logger.debug("User message saved for thread_id: %s", thread_id)

        Logger.debug("Fetching thread for thread_id: %s", thread_id)

        thread = await get_thread_by_id(session, thread_id, user_id)

        if not thread:
            raise ValueError("Thread not found")

        Logger.debug("Building history for thread_id: %s", thread_id)

        history = self.build_history(thread.messages)
        llama = get_llama_pipeline(model)

        response = ""
        is_assistant_message_saved = False

        async def save_assistant_response(__session: AsyncSession):
            nonlocal is_assistant_message_saved, response

            if is_assistant_message_saved:
                return

            Logger.debug("Saving assistant message for thread_id: %s", thread_id)

            await self.save_message(
                __session,
                user_id,
                message=response,
                role="assistant",
                thread_id=thread_id,
            )

            await __session.commit()

            is_assistant_message_saved = True

        async def stream_response_accumulator() -> AsyncGenerator[str, None]:
            nonlocal response

            yield (
                StreamingBlock(
                    chunk=None, event="user_message_insert", thread_id=thread_id
                ).model_dump_json(by_alias=True)
                + "\n"
            )

            async for chunk in llama.chat_completion_stream(history):
                if get_stop_signal is not None and await get_stop_signal():
                    Logger.error("Streaming interrupted by client for thread_id: %s", thread_id)
                    break

                response += chunk

                yield (
                    StreamingBlock(
                        chunk=chunk, event="new_chunk", thread_id=None
                    ).model_dump_json(by_alias=True)
                    + "\n"
                )

            Logger.debug("Streaming completed for thread_id: %s", thread_id)

            await save_assistant_response(session)

            yield (
                StreamingBlock(
                    chunk=None, event="assistant_message_insert", thread_id=thread_id
                ).model_dump_json(by_alias=True)
                + "\n"
            )

            yield (
                StreamingBlock(chunk=None, event="done", thread_id=None).model_dump_json(
                    by_alias=True
                )
                + "\n"
            )

        async def background_task(__session: AsyncSession):
            try:
                await save_assistant_response(__session)
            except Exception as e:
                Logger.error(
                    "Error in background_task for thread_id: %s, error: %s", thread_id, str(e)
                )

        return stream_response_accumulator(), background_task
