from typing import Annotated, Literal

from annotated_types import MinLen
from pydantic import BaseModel, Field


class UserChatRequest(BaseModel):
    message: Annotated[str, MinLen(1)]
    thread_id: Annotated[str | None, Field(alias="threadId")] = None
    enable_thinking: Annotated[bool | None, Field(alias="enableThinking")] = None


class ThreadRequest(BaseModel):
    thread_id: Annotated[str, Field(alias="threadId")]
    enable_thinking: Annotated[bool | None, Field(alias="enableThinking")] = None


class UserChatResponse(BaseModel):
    response: str
    thread_id: Annotated[str, Field(serialization_alias="threadId")]


class StreamingBlock(BaseModel):
    chunk: str | None
    event: Literal[
        "user_message_insert",
        "assistant_message_insert",
        "new_chunk",
        "new_thinking_chunk",
        "done",
    ]
    thread_id: Annotated[str | None, Field(serialization_alias="threadId")] = None
