from typing import Annotated

from pydantic import UUID4, BaseModel, EmailStr


class GetUserResponse(BaseModel):
    id: Annotated[str, UUID4]
    name: str
    email: EmailStr
