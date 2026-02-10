import datetime
from typing import Annotated

from pydantic import BaseModel, Field
from pydantic import UUID4


class GetAllThreadsRequest(BaseModel):
    pass


class ThreadMetadata(BaseModel):
    id: Annotated[str, UUID4]
    title: str
    creation_date: Annotated[datetime.date, Field(serialization_alias="creationDate")]
    update_time: Annotated[datetime.datetime, Field(serialization_alias="updateTime")]


class GetAllThreadsResponse(BaseModel):
    threads: list[ThreadMetadata]


class ResponseMessage(BaseModel):
    inline_value: Annotated[str, Field(serialization_alias="content")]
    role: str


class GetThreadResponse(ThreadMetadata):
    messages: list[ResponseMessage]
