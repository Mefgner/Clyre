from types import NoneType
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.params import Depends

from schemas.auth import UserRegisterRequest, UserLoginRequest, TelegramRegistrationRequest
from services.auth import AuthService
from utils.web import extract_service_token

auth_router = APIRouter(tags=["auth"])
auth_sc = AuthService()


@auth_router.post("/login")
async def login(response: Response, login_data: Annotated[UserLoginRequest, Body()]):
    try:
        access, refresh = await auth_sc.login_locally(**login_data.model_dump())
        response.set_cookie("refresh_token", refresh.token, expires=refresh.expires, httponly=True)
        return access
    except ValueError as e:
        return HTTPException(status_code=400, detail=str(e))


@auth_router.post("/register")
async def register(response: Response, registration_data: Annotated[UserRegisterRequest, Body()]):
    try:
        access, refresh = await auth_sc.register_locally(**registration_data.model_dump())
        response.set_cookie("refresh_token", refresh.token, expires=refresh.expires, httponly=True)
        return access
    except ValueError as e:
        return HTTPException(status_code=400, detail=str(e))


@auth_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out"}


@auth_router.post("/refresh")
async def refresh_access(response: Response):
    ...  # TODO: Implement refresh token logic


@auth_router.post('/telegram-register')
async def telegram_register(request: TelegramRegistrationRequest,
                            _: Annotated[NoneType, Depends(extract_service_token)]):
    try:
        await auth_sc.register_telegram(request.user_id, request.chat_id)
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=209, detail="Telegram account already exists")
        raise HTTPException(status_code=400, detail=str(e))
