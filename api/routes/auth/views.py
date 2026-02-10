import re
import logging
from typing import Annotated

from email_validator import validate_email, EmailNotValidError
from fastapi import APIRouter, HTTPException, Response
from fastapi.params import Depends, Body
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


def check_auth(auth_data: UserLoginRequest):
    try:
        if not validate_email(auth_data.email):
            raise HTTPException(status_code=422, detail="Invalid email")
    except EmailNotValidError:
        raise HTTPException(status_code=422, detail="Invalid email")

    if not auth_data.password:
        raise HTTPException(status_code=422, detail="Password is required")

    if len(auth_data.password) < 8:
        raise HTTPException(
            status_code=422, detail="Password must be at least 8 characters long"
        )

    if not re.search(r"[A-Z]", auth_data.password):
        raise HTTPException(
            status_code=422, detail="Password must contain at least one uppercase letter"
        )

    if not re.search(r"[a-z]", auth_data.password):
        raise HTTPException(
            status_code=422, detail="Password must contain at least one lowercase letter"
        )

    if not re.search(r"\d", auth_data.password):
        raise HTTPException(status_code=422, detail="Password must contain at least one digit")

    if not re.search(r"\W", auth_data.password):
        raise HTTPException(
            status_code=422, detail="Password must contain at least one special character"
        )


def check_register(auth_data: UserRegisterRequest):
    check_auth(auth_data)

    if len(auth_data.name) not in range(3, 31):
        raise HTTPException(
            status_code=422, detail="Name must be between 3 and 30 characters long"
        )

    if not re.match(r"^[\w_]+$", auth_data.name):
        raise HTTPException(
            status_code=422, detail="Name can only contain letters, numbers and underscores"
        )


@auth_router.post("/login", response_model=LoginResponse, status_code=200)
async def login(
    response: Response,
    login_data: Annotated[UserLoginRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):

    check_auth(login_data)

    try:
        Logger.info("Processing login request from %s", login_data.email or "unknown user")
        access, refresh = await auth_sc.login_locally(session, **login_data.model_dump())
        response.set_cookie(
            "refresh_token", refresh.token, expires=refresh.expires, httponly=True
        )
        return LoginResponse(token=access.token)
    except ValueError as e:
        Logger.error("Login failed for %s: %s", login_data.email or "unknown user", e)
        raise HTTPException(status_code=400, detail=str(e))


@auth_router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    response: Response,
    registration_data: Annotated[UserRegisterRequest, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):

    check_register(registration_data)

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
        Logger.error("Registration failed for %s: %s", registration_data.email, e)
        raise HTTPException(status_code=400, detail=str(e))


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
