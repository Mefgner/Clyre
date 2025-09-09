import os
from datetime import datetime, timezone

from fastapi import APIRouter

from api.schemas import UserChatRequest
from services.chat import ChattingService

router = APIRouter(prefix="/api", tags=["core"])

chatting_sc = ChattingService()


@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/version")
def version():
    return {"app": "clyre-backend", "version": os.getenv("CLYRE_VERSION", "0.0.1")}


@router.post("/chat-response")
async def chat_response(request: UserChatRequest):
    message, thread = await chatting_sc.send_message(request.user_id, request.message)
    response = await chatting_sc.generate_llm_response(message.id, thread.id)
    return {"response": response.inline_value}
