from db import SessionManager
from models import Message, Thread
from pipelines.llama import get_llama_pipeline
from crud import create_message, create_thread, get_message_by_id, get_last_message_in_thread


class ChattingService:
    @staticmethod
    async def send_message(user_id: int, message_text: str, thread: Thread | None = None) -> tuple[Message, Thread]:
        sm = SessionManager()
        async with sm.get_session_context_manager() as session:
            if thread is None:
                thread = await create_thread(session, user_id=user_id, title="New Thread")
                await session.flush()  # Ensure thread.id is populated
                last_order = -1
            else:
                last_order = (await get_last_message_in_thread(session, thread)).order

            new_message = await create_message(
                session, user_id=user_id, thread_id=thread.id, role="user", content=message_text, order=last_order + 1
            )
        return new_message, thread

    @staticmethod
    async def generate_llm_response(message_id: int, thread_id: int, model: str = '') -> Message:
        llama = get_llama_pipeline(model)
        sm = SessionManager()
        async with sm.get_session_context_manager() as session:
            message = await get_message_by_id(session, message_id)
            if not message:
                raise ValueError("Message not found")
            prompt = message.inline_value
            response_data = await llama.chat_completion_sync(prompt=prompt)
            response_message = await create_message(
                session, user_id=message.user_id, thread_id=thread_id, role="assistant", content=response_data['choices'][0]['message']['content'],
                order=message.order + 1
            )
        return response_message
