from typing import Annotated

from annotated_types import Len
from pydantic import BaseModel, EmailStr, Field


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Len(8, 30)] = Field(pattern=r"[\w\d!@#$%^&*()_\+\/\-\*\+]{8,}")


class TelegramRegistrationRequest(BaseModel):
    user_id: str
    chat_id: str


class UserRegisterRequest(UserLoginRequest):
    name: Annotated[str, Len(5, 90)]
