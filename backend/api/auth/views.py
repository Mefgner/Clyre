import logging
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db_session
from schemas.auth import (
    UserLoginRequest,
    UserRegisterRequest,
    LogoutResponse,
    RefreshResponse,
    RegisterResponse,
    LoginResponse,
)
from schemas.general import TokenPayload
from services.auth import AuthService
from utils import web

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)
auth_router = APIRouter(tags=["auth"])
auth_sc = AuthService()


@auth_router.post("/login", response_model=LoginResponse, status_code=200)
async def login(
    response: Response,
    login_data: Annotated[UserLoginRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        Logger.info("Processing login request from %s", login_data.email or "unknown user")
        access, refresh = await auth_sc.login_locally(session, **login_data.model_dump())
        response.set_cookie(
            "refresh_token", refresh.token, expires=refresh.expires, httponly=True
        )
        return LoginResponse(token=access.token)
    except ValueError as e:
        Logger.error("Login failed for %s: %s", login_data.email or "unknown user", e)
        return HTTPException(status_code=400, detail=str(e))


@auth_router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    response: Response,
    registration_data: Annotated[UserRegisterRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        Logger.info("Processing registration request from %s", registration_data.email)
        access, refresh = await auth_sc.register_locally(
            session, **registration_data.model_dump()
        )

        await session.commit()

        response.set_cookie(
            "refresh_token", refresh.token, expires=refresh.expires, httponly=True
        )
        return RegisterResponse(token=access.token)
    except ValueError as e:
        return HTTPException(status_code=400, detail=str(e))


@auth_router.post("/logout", response_model=LogoutResponse, status_code=200)
async def logout(response: Response):
    Logger.info("Processing logout request")
    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out"}


@auth_router.post("/refresh", response_model=RefreshResponse, status_code=200)
async def refresh_access(
    response: Response,
    refresh_payload: Annotated[TokenPayload, Depends(web.extract_refresh_token)],
):
    Logger.info("Processing refresh request")
    access, refresh = await auth_sc.refresh_token(refresh_payload)
    response.set_cookie("refresh_token", refresh.token, expires=refresh.expires, httponly=True)
    return RefreshResponse(token=access.token)


# @auth_router.post("/telegram-register")
# async def telegram_register(
#     request: TelegramRegistrationRequest,
#     _: Annotated[NoneType, Depends(web.extract_service_token)],
#     session: Annotated[AsyncSession, Depends(get_db_session)],
# ):
#     try:
#         Logger.info("Processing telegram registration request from %s", request.user_id)
#         await auth_sc.register_telegram(session, request.user_id, request.chat_id)
#     except ValueError as exc:
#         if "already exists" in str(exc):
#             raise HTTPException(
#                 status_code=209, detail="Telegram account already exists"
#             ) from exc
#         raise HTTPException(status_code=400, detail=str(exc)) from exc
