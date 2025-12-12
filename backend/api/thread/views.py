import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db_session
from schemas.general import TokenPayload
from schemas.thread import GetAllThreadsResponse, GetThreadResponse
from services.thread import ThreadService
from utils import web

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)
thread_router = APIRouter(tags=["thread"])

thread_sc = ThreadService()


@thread_router.get("/all", response_model=GetAllThreadsResponse)
async def all_users_threads(
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    Logger.info("Getting all threads from user %s", token_payload.user_id)
    user_id = token_payload.user_id
    try:
        threads = await thread_sc.all_thread_meta(session, user_id)
        return {"threads": threads}
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Thread not found") from e


@thread_router.get("/{thread_id}", response_model=GetThreadResponse)
async def get_thread_by_id(
    thread_id: str,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    Logger.info("Getting thread %s from user %s", thread_id, token_payload.user_id)
    user_id = token_payload.user_id
    try:
        return await thread_sc.thread_by_id(session, user_id, thread_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Thread not found") from e


@thread_router.delete("/{thread_id}")
async def delete_thread(
    thread_id: str,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    Logger.info("Deleting thread %s from user %s", thread_id, token_payload.user_id)
    user_id = token_payload.user_id
    try:
        await thread_sc.delete_thread(session, user_id, thread_id)
        return {"result": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Thread not found") from e
