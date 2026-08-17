from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=45)


class ProjectUpdateRequest(ProjectCreateRequest):
    pass


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str


__all__ = ["ProjectCreateRequest", "ProjectResponse", "ProjectUpdateRequest"]
