from fastapi import APIRouter

from api.schemas import UserChatRequest
from services.chat import ChattingService

chatting_sc = ChattingService()
chat_router = APIRouter(prefix="/chat", tags=["chatting"])


@chat_router.post("/response-sync")
async def chat_response(request: UserChatRequest):
    message_id, thread_id = await chatting_sc.send_message(request.user_id, request.message, request.thread_id)
    response = await chatting_sc.generate_llm_response(thread_id, request.user_id)
    return {"response": response.inline_value, "thread_id": thread_id, "message_id": message_id}
