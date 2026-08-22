import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import StreamingResponse

from crud import get_thread_by_id
from db import get_db_session
from schemas.chatting import ThreadRequest, UserChatRequest, UserChatResponse
from schemas.general import TokenPayload
from services.chatting import ChattingService
from services.generation import GenerationConflict
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
    offset: int = 0,
):
    Logger.info(
        "chat_stream request from %s to thread %s (offset=%s)",
        token_payload.user_id,
        request.thread_id or "(Create new thread)",
        offset,
    )

    user_id = token_payload.user_id
    thread_id = request.thread_id
    message = request.message

    try:
        run = await chatting_sc.start_generation(
            session,
            thread_id,
            user_id,
            message,
            enable_thinking=request.enable_thinking,
        )

        async def stream():
            async for line in run.subscribe(offset):
                yield line

        return StreamingResponse(stream(), media_type="application/x-ndjson")
    except GenerationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError:
        raise HTTPException(status_code=400, detail="Thread not found")


@chat_router.post("/stop")
async def stop_generation(
    request: ThreadRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    Logger.info(
        "chat_stop request from %s for thread %s", token_payload.user_id, request.thread_id
    )

    thread = await get_thread_by_id(session, request.thread_id, token_payload.user_id)
    if not thread:
        Logger.warning(
            "Stop for foreign or missing thread=%s user=%s",
            request.thread_id,
            token_payload.user_id,
        )
        raise HTTPException(status_code=404, detail="Thread not found")

    if not chatting_sc.stop_generation(request.thread_id):
        raise HTTPException(status_code=409, detail="No active generation for this thread")

    return {"result": "stopping"}


@chat_router.post("/retry")
async def retry_generation(
    request: ThreadRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    Logger.info(
        "chat_retry request from %s for thread %s", token_payload.user_id, request.thread_id
    )

    try:
        run = await chatting_sc.retry_generation(
            session,
            request.thread_id,
            token_payload.user_id,
            enable_thinking=request.enable_thinking,
        )

        async def stream():
            async for line in run.subscribe(0):
                yield line

        return StreamingResponse(stream(), media_type="application/x-ndjson")
    except GenerationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError:
        raise HTTPException(status_code=400, detail="Thread not found")
