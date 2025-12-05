import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends

from schemas.general import TokenPayload
from schemas.thread import GetAllThreadsResponse
from services.thread import ThreadService
from utils import web

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)
thread_router = APIRouter(tags=["thread"])

thread_sc = ThreadService()


@thread_router.get("/all", response_model=GetAllThreadsResponse)
async def all_users_threads(
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
):
    Logger.info("Getting all threads from user %s", token_payload.user_id)
    user_id = token_payload.user_id
    try:
        threads = await thread_sc.threads_from_user(user_id)
        return {"threads": threads}
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Thread not found") from e
