from typing import Annotated

from annotated_types import MinLen
from pydantic import BaseModel


class UserChatRequest(BaseModel):
    message: Annotated[str, MinLen(1)]
    thread_id: str | None = None


class TelegramBotChatRequest(UserChatRequest):
    telegram_user_id: str
    telegram_chat_id: str
