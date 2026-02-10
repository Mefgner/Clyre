import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db_session
from schemas.general import TokenPayload
from schemas.user import GetUserResponse
from services.user import UserService
from utils import web

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)
user_router = APIRouter(tags=["user"])

user_sc = UserService()


@user_router.get("/me", response_model=GetUserResponse)
async def get_user(
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    Logger.info("Getting user info %s", token_payload.user_id)

    user_id = token_payload.user_id

    try:
        user_info = await user_sc.get_local_conn_from_internal_user(session, user_id)
        return user_info

    except Exception as e:
        raise HTTPException(status_code=404, detail="User does not exist") from e
