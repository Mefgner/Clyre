from types import NoneType
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends

from schemas.chatting import UserChatRequest, TelegramBotChatRequest
from schemas.general import TokenPayload
from services.chatting import ChattingService
from services.connection import ConnectionService
from utils import web

chatting_sc = ChattingService()
connection_sc = ConnectionService()
chat_router = APIRouter(tags=["chatting"])


@chat_router.post("/response")
async def chat_response(
        request: UserChatRequest,
        token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)]):
    user_id = token_payload.user_id
    message_id, thread_id = await chatting_sc.send_message(user_id, request.message, request.thread_id)
    response = await chatting_sc.generate_llm_response(thread_id, user_id)
    return {"response": response.inline_value, "thread_id": thread_id, "message_id": message_id}


@chat_router.post("/telegram-response")
async def telegram_response(request: TelegramBotChatRequest, _: Annotated[NoneType, Depends(web.extract_service_token)]):
    try:
        user_id = await connection_sc.user_from_telegram(request.telegram_user_id, request.telegram_chat_id)
    except ValueError:
        raise HTTPException(401, detail="User not found. Please register first or login with your Telegram account.")
    message_id, thread_id = await chatting_sc.send_message(user_id, request.message, request.thread_id)
    response = await chatting_sc.generate_llm_response(thread_id, user_id)
    return {"response": response.inline_value, "thread_id": thread_id, "message_id": message_id}
