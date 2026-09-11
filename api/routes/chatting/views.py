import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.params import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from crud import get_thread_by_id
from db import get_db_session
from models import Message
from pipelines.inference import BudgetServiceUnavailable, ContextLimitExceeded
from schemas.chatting import ThreadRequest, UserChatRequest, UserChatResponse
from schemas.general import TokenPayload
from services.chat_context import AttachedFileError, AttachmentLimitExceeded
from services.chatting import ChattingService
from services.generation import GenerationConflict, get_run
from utils import web

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)
chatting_sc = ChattingService()
chat_router = APIRouter(tags=["chatting"])


def _limit_detail(has_files: bool) -> dict[str, str]:
    if has_files:
        message = (
            "The required prompt and attached files exceed the current model context limit. "
            "Remove a file, attach a smaller version, or shorten the request."
        )
    else:
        message = (
            "The required prompt and current request exceed the model context limit. "
            "Shorten the request or use a model with a larger context window."
        )
    return {"code": "context_limit_exceeded", "message": message}


def _map_start_error(exc: Exception, *, has_files: bool) -> HTTPException:
    if isinstance(exc, GenerationConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ContextLimitExceeded):
        return HTTPException(status_code=422, detail=_limit_detail(has_files))
    if isinstance(exc, BudgetServiceUnavailable):
        return HTTPException(
            status_code=503, detail="Model budget check is temporarily unavailable"
        )
    if isinstance(exc, (AttachedFileError, AttachmentLimitExceeded)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ValueError):
        # Foreign and missing threads/files share one 404; ownership is
        # checked before activity so no state leaks via 409-vs-404.
        return HTTPException(status_code=404, detail=str(exc))
    raise exc


@chat_router.post("/response", response_model=UserChatResponse)
async def chat_response(
    request: UserChatRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Legacy non-streaming wrapper over the single generation-start path."""
    Logger.info(
        "chat_response request from %s to thread %s",
        token_payload.user_id,
        request.thread_id or "(Create new thread)",
    )
    user_id = token_payload.user_id
    try:
        run = await chatting_sc.start_generation(
            session,
            request.thread_id,
            user_id,
            request.message,
            enable_thinking=request.enable_thinking,
            file_ids=request.file_ids,
        )
    except Exception as exc:
        raise _map_start_error(exc, has_files=bool(request.file_ids)) from exc
    await run.wait_done()
    if run.status.value != "finished":
        raise HTTPException(status_code=500, detail="Generation failed. Please try again.")
    result = await session.execute(
        select(Message)
        .where(Message.thread_id == run.thread_id, Message.user_id == user_id)
        .order_by(Message.order.desc())
        .limit(1)
    )
    assistant = result.scalars().first()
    return {
        "response": assistant.inline_value if assistant and assistant.inline_value else "",
        "thread_id": run.thread_id,
    }


# No response model because the service dumps StreamBlock to string.
@chat_router.post("/stream")
async def stream_response(
    request: UserChatRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    Logger.info(
        "chat_stream request from %s to thread %s",
        token_payload.user_id,
        request.thread_id or "(Create new thread)",
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
            file_ids=request.file_ids,
        )

        async def stream():
            async for line in run.subscribe(0):
                yield line

        return StreamingResponse(
            stream(),
            media_type="application/x-ndjson",
            headers={"X-Clyre-Thread-Id": run.thread_id},
        )
    except Exception as exc:
        raise _map_start_error(exc, has_files=bool(request.file_ids)) from exc


@chat_router.get("/stream/{thread_id}")
async def attach_stream(
    thread_id: str,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Subscribe to a buffered generation without starting another one."""
    thread = await get_thread_by_id(session, thread_id, token_payload.user_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    run = get_run(thread_id)
    if run is None:
        raise HTTPException(status_code=410, detail="Generation stream is no longer available")
    if offset > run.event_count:
        raise HTTPException(status_code=416, detail="Offset exceeds available events")

    Logger.info(
        "chat_stream attach from %s to thread %s (offset=%s)",
        token_payload.user_id,
        thread_id,
        offset,
    )

    async def stream():
        async for line in run.subscribe(offset):
            yield line

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"X-Clyre-Thread-Id": thread_id},
    )


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
        # "Nothing to retry" and active-generation conflicts share 409.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ContextLimitExceeded as exc:
        raise HTTPException(status_code=422, detail=_limit_detail(False)) from exc
    except BudgetServiceUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Model budget check is temporarily unavailable"
        ) from exc
    except (AttachedFileError, AttachmentLimitExceeded) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc
