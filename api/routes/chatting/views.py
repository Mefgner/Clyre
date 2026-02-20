import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import StreamingResponse

from db import get_db_session
from schemas.chatting import UserChatRequest, UserChatResponse
from schemas.general import TokenPayload
from services.chatting import ChattingService
from utils import web

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)
chatting_sc = ChattingService()
chat_router = APIRouter(tags=["chatting"])


@chat_router.post("/response", response_model=UserChatResponse)
async def chat_response(
    request: UserChatRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    Logger.info(
        "chat_response request from %s to thread %s",
        token_payload.user_id,
        request.thread_id or "(Create new thread)",
    )
    user_id = token_payload.user_id
    _, thread_id = await chatting_sc.save_message(
        session, user_id, request.message, "user", request.thread_id
    )
    await session.commit()
    response_message, _ = await chatting_sc.generate_llm_response(session, thread_id, user_id)
    return {
        "response": response_message.inline_value,
        "thread_id": thread_id,
    }


# No response model because the service dumps StreamBlock to string.
@chat_router.post("/stream")
async def stream_response(
    starlette_request: Request,
    request: UserChatRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    background_tasks: BackgroundTasks,
):
    Logger.info(
        "chat_response request from %s to thread %s",
        token_payload.user_id,
        request.thread_id or "(Create new thread)",
    )

    user_id = token_payload.user_id
    thread_id = request.thread_id
    message = request.message

    try:
        generator, after_generation_task = await chatting_sc.stream_response(
            session, thread_id, user_id, message, starlette_request.is_disconnected
        )

        background_tasks.add_task(after_generation_task, session)

        return StreamingResponse(generator, media_type="application/x-ndjson")
    except ValueError:
        raise HTTPException(status_code=400, detail="Thread not found")
    except Exception:
        raise


# @chat_router.post("/telegram-response")
# async def telegram_response(
#     request: TelegramBotChatRequest,
#     _: Annotated[None, Depends(web.extract_service_token)],
#     session: Annotated[AsyncSession, Depends(get_db_session)],
# ):
#     try:
#         user_id = await connection_sc.user_from_telegram(
#             session, request.telegram_user_id, request.telegram_chat_id
#         )
#     except ValueError as exc:
#         raise HTTPException(
#             404,
#             detail="User not found. Please register first or login with your Telegram account.",
#         ) from exc
#     Logger.info(
#         "chat_response (telegram) request from %s to thread %s",
#         user_id,
#         request.thread_id or "(Create new thread)",
#     )
#     _, thread_id = await chatting_sc.send_message(
#         session, user_id, request.message, request.thread_id
#     )
#     await session.flush()
#     response = await chatting_sc.generate_llm_response(session, thread_id, user_id)
#     return {"response": response.inline_value, "thread_id": thread_id}
#
#
# @chat_router.post("/telegram-stream")
# async def telegram_stream(
#     request: TelegramBotChatRequest,
#     _: Annotated[None, Depends(web.extract_service_token)],
#     session: Annotated[AsyncSession, Depends(get_db_session)],
# ):
#     try:
#         user_id = await connection_sc.user_from_telegram(
#             session, request.telegram_user_id, request.telegram_chat_id
#         )
#     except ValueError as exc:
#         raise HTTPException(
#             404,
#             detail="User not found. Please register first or login with your Telegram account.",
#         ) from exc
#     Logger.info(
#         "chat_stream (telegram) request from %s to thread %s",
#         user_id,
#         request.thread_id or "(Create new thread)",
#     )
#     _, thread_id = await chatting_sc.send_message(
#         session, user_id, request.message, request.thread_id
#     )
#     await session.flush()
#     return StreamingResponse(
#         chatting_sc.stream_response(session, thread_id, user_id), media_type="text/event-stream"
#     )
