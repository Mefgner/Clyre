import datetime
from typing import Annotated

from pydantic import UUID4, BaseModel, Field


class GetAllThreadsRequest(BaseModel):
    pass


class ThreadMetadata(BaseModel):
    id: Annotated[str, UUID4]
    title: str
    creation_date: Annotated[datetime.date, Field(serialization_alias="creationDate")]
    update_time: Annotated[datetime.datetime, Field(serialization_alias="updateTime")]
    is_generating: Annotated[bool, Field(serialization_alias="isGenerating")] = False


class GetAllThreadsResponse(BaseModel):
    threads: list[ThreadMetadata]


class ResponseMessage(BaseModel):
    inline_value: Annotated[str | None, Field(serialization_alias="content")] = None
    thinking_value: Annotated[str | None, Field(serialization_alias="thinking")] = None
    role: str


class GetThreadResponse(ThreadMetadata):
    messages: list[ResponseMessage]
