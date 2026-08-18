from typing import Annotated

from fastapi.security import HTTPBearer
from pydantic import UUID4, BaseModel


class TokenPayload(BaseModel):
    user_id: Annotated[str, UUID4]
    timestamp: float
    refresh_token_id: Annotated[str, UUID4] | None = None


security_scheme = HTTPBearer(bearerFormat="Service", scheme_name="Service")
