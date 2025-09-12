from pydantic import BaseModel


class UserChatRequest(BaseModel):
    message: str
    user_id: str
    thread_id: str | None = None