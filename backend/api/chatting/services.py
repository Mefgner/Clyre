from typing import Iterable

from crud import create_message, create_thread, get_messages_in_thread
from crud.message import get_last_message_order_in_thread
from db import SessionManager
from models import Message
from pipelines.llama import get_llama_pipeline


class ChattingService:
    @classmethod
    async def send_message(cls, user_id: str, message_text: str, thread_id: str | None = None) -> tuple[
        str, str]:
        sm = SessionManager()
        async with sm.get_session_context_manager() as session:
            if not thread_id:
                thread = await create_thread(session, user_id=user_id, title="New Thread")
                await session.flush()  # Ensure thread.id is populated
                thread_id = thread.id
                last_order = -1
            else:
                last_order = await get_last_message_order_in_thread(session, thread_id=thread_id)

            new_message = await create_message(
                session, user_id=user_id, thread_id=thread_id, role="user", content=message_text, order=last_order + 1
            )
            await session.flush()  # Ensure new_message.id is populated
            return new_message.id, thread_id

    @classmethod
    def build_history(cls, messages: Iterable[Message]) -> list[dict[str, str]]:
        history = []
        for msg in messages:
            history.append({"role": msg.role, "content": msg.inline_value})
        return history

    @classmethod
    async def generate_llm_response(cls, thread_id: str, user_id: str, model: str = '') -> Message:
        llama = get_llama_pipeline(model)
        sm = SessionManager()

        async with sm.get_session_context_manager() as session:
            messages = await get_messages_in_thread(session, thread_id)
            if not messages:
                raise ValueError("Message not found")

            history = cls.build_history(messages)
            response_data = await llama.chat_completion_sync(history)
            response_message = await create_message(
                session, user_id=user_id, thread_id=thread_id, role="assistant",
                content=response_data['choices'][0]['message']['content'],
                order=await get_last_message_order_in_thread(session, thread_id)
            )
        return response_message
