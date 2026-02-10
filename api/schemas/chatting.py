from typing import Annotated, Literal

from annotated_types import MinLen
from pydantic import BaseModel, Field


class UserChatRequest(BaseModel):
    message: Annotated[str, MinLen(1)]
    thread_id: Annotated[str | None, Field(alias="threadId")] = None


class UserChatResponse(BaseModel):
    response: str
    thread_id: Annotated[str, Field(serialization_alias="threadId")]


class StreamingBlock(BaseModel):
    chunk: str | None
    event: Literal["user_message_insert", "assistant_message_insert", "new_chunk", "done"]
    thread_id: Annotated[str | None, Field(serialization_alias="threadId")] = None


class TelegramBotChatRequest(UserChatRequest):
    telegram_user_id: str
    telegram_chat_id: str
