import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from starlette.responses import StreamingResponse

from schemas.chatting import TelegramBotChatRequest, UserChatRequest
from schemas.general import TokenPayload
from services.chatting import ChattingService
from services.connection import ConnectionService
from utils import web

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)
chatting_sc = ChattingService()
connection_sc = ConnectionService()
chat_router = APIRouter(tags=["chatting"])


@chat_router.post("/response")
async def chat_response(
    request: UserChatRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
):
    Logger.info(
        "chat_response request from %s to thread %s",
        token_payload.user_id,
        request.thread_id or "(Create new thread)",
    )
    user_id = token_payload.user_id
    _, thread_id = await chatting_sc.send_message(user_id, request.message, request.thread_id)
    response = await chatting_sc.generate_llm_response(thread_id, user_id)
    return {
        "response": response.inline_value,
        "thread_id": thread_id,
    }


@chat_router.post("/stream")
async def stream_response(
    request: UserChatRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
):
    Logger.info(
        "chat_response request from %s to thread %s",
        token_payload.user_id,
        request.thread_id or "(Create new thread)",
    )
    user_id = token_payload.user_id
    _, thread_id = await chatting_sc.send_message(user_id, request.message, request.thread_id)
    return StreamingResponse(
        chatting_sc.stream_response(thread_id, user_id), media_type="text/event-stream"
    )


@chat_router.post("/telegram-response")
async def telegram_response(
    request: TelegramBotChatRequest,
    _: Annotated[None, Depends(web.extract_service_token)],
):
    try:
        user_id = await connection_sc.user_from_telegram(
            request.telegram_user_id, request.telegram_chat_id
        )
    except ValueError as exc:
        raise HTTPException(
            404,
            detail="User not found. Please register first or login with your Telegram account.",
        ) from exc
    Logger.info(
        "chat_response (telegram) request from %s to thread %s",
        user_id,
        request.thread_id or "(Create new thread)",
    )
    _, thread_id = await chatting_sc.send_message(user_id, request.message, request.thread_id)
    response = await chatting_sc.generate_llm_response(thread_id, user_id)
    return {"response": response.inline_value, "thread_id": thread_id}


@chat_router.post("/telegram-stream")
async def telegram_stream(
    request: TelegramBotChatRequest,
    _: Annotated[None, Depends(web.extract_service_token)],
):
    try:
        user_id = await connection_sc.user_from_telegram(
            request.telegram_user_id, request.telegram_chat_id
        )
    except ValueError as exc:
        raise HTTPException(
            404,
            detail="User not found. Please register first or login with your Telegram account.",
        ) from exc
    Logger.info(
        "chat_stream (telegram) request from %s to thread %s",
        user_id,
        request.thread_id or "(Create new thread)",
    )
    _, thread_id = await chatting_sc.send_message(user_id, request.message, request.thread_id)
    return StreamingResponse(
        chatting_sc.stream_response(thread_id, user_id), media_type="text/event-stream"
    )
