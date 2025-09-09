from pydantic import BaseModel


class UserChatRequest(BaseModel):
    message: str
    user_id: int
    thread_id: int | None = None
    model: str | None = None