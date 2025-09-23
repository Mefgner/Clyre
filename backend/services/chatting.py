import json
import logging
from collections.abc import AsyncGenerator, Iterable

from crud import (
    create_message,
    create_thread,
    get_messages_in_thread,
    get_thread_by_id,
    update_thread_time,
)
from crud.message import get_last_message_order_in_thread
from db import get_session_manager
from models import Message, Thread
from pipelines.llama import get_llama_pipeline
from utils import timing

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)


class ChattingService:
    @staticmethod
    async def send_message(
        user_id: str, message: str, thread_id: str | None = None
    ) -> tuple[str, str]:
        thread: Thread | None = None
        sm = get_session_manager()
        async with sm.context_manager as session:
            if not thread_id:
                thread = await create_thread(session, user_id=user_id, title="New Thread")
                thread_id = thread.id
                last_order = -1
            else:
                last_order = await get_last_message_order_in_thread(
                    session, thread_id=thread_id, user_id=user_id
                )

            if not thread:
                thread = await get_thread_by_id(session, thread_id)
            await update_thread_time(session, thread, timing.get_utc_now())

            new_message = await create_message(
                session,
                user_id=user_id,
                thread_id=thread_id,
                role="user",
                content=message,
                order=last_order + 1,
            )
            return new_message.id, thread_id

    @staticmethod
    def build_history(messages: Iterable[Message]) -> list[dict[str, str]]:
        history = []
        for msg in messages:
            history.append({"role": msg.role, "content": msg.inline_value})
        return history

    async def generate_llm_response(
        self, thread_id: str, user_id: str, model: str = ""
    ) -> Message:
        llama = get_llama_pipeline(model)
        sm = get_session_manager()

        async with sm.context_manager as session:
            messages = await get_messages_in_thread(session, thread_id, user_id)
            if not messages:
                raise ValueError("Message not found")

            thread = await get_thread_by_id(session, thread_id)
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
        return response_message

    async def stream_response(
        self, thread_id: str, user_id: str, model: str = ""
    ) -> AsyncGenerator[str, None]:
        llama = get_llama_pipeline(model)
        sm = get_session_manager()

        async with sm.context_manager as session:
            messages = await get_messages_in_thread(session, thread_id, user_id)
            if not messages:
                raise ValueError("Message not found")

            thread = await get_thread_by_id(session, thread_id)
            await update_thread_time(session, thread, timing.get_utc_now())

            history = self.build_history(messages)
            response: str = ""
            async for token in llama.chat_completion_stream(history):
                response += token
                yield json.dumps({"token": token}) + "\n"

            response_message = await create_message(
                session,
                user_id=user_id,
                thread_id=thread_id,
                role="assistant",
                content=response,
                order=await get_last_message_order_in_thread(session, thread_id, user_id) + 1,
            )

            yield json.dumps(
                {
                    "token": None,
                    "done": True,
                    "thread_id": thread_id,
                    "message_id": response_message.id,
                }
            )
