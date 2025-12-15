from typing import Annotated

from annotated_types import Len
from pydantic import BaseModel, EmailStr, Field


class UserLoginRequest(BaseModel):
    email: str
    password: str


class TelegramRegistrationRequest(BaseModel):
    user_id: str
    chat_id: str


class UserRegisterRequest(UserLoginRequest):
    name: Annotated[str, Len(5, 90)]


class __TokenResponse(BaseModel):
    token: str


class LoginResponse(__TokenResponse):
    pass


class RegisterResponse(__TokenResponse):
    pass


class RefreshResponse(__TokenResponse):
    pass


class LogoutResponse(BaseModel):
    message: str = Field(
        default="Logout successful", description="Message indicating successful logout"
    )
