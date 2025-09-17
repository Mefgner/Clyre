from typing import Annotated

from pydantic import BaseModel, UUID4


class UserChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class TelegramBotChatRequest(BaseModel):
    telegram_user_id: str
    telegram_chat_id: str
    message: str
    thread_id: str | None = None
