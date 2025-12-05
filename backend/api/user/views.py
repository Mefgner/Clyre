import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends

from schemas.general import TokenPayload
from services.user import UserService
from utils import web

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)
user_router = APIRouter(tags=["user"])

user_sc = UserService()


@user_router.get("/user-info")
async def get_user(token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)]):
    Logger.info("Getting user info %s", token_payload.user_id)

    user_id = token_payload.user_id

    try:
        user_info = await user_sc.get_user_by_id(user_id)
        return user_info

    except Exception as e:
        raise HTTPException(status_code=404, detail="User does not exist") from e
