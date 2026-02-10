from typing import Annotated

from pydantic import BaseModel, EmailStr, UUID4


class GetUserResponse(BaseModel):
    id: Annotated[str, UUID4]
    name: str
    email: EmailStr
