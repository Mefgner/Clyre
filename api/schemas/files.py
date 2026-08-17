from datetime import date

from pydantic import BaseModel, ConfigDict


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    content_type: str
    head_value: str | None
    creation_date: date | None
    project_id: str | None
    index_status: str
    index_error: str | None


__all__ = ["FileResponse"]
