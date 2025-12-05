from crud import get_public_local_conn_by_user_id
from db import get_session_manager


class UserService:
    @staticmethod
    async def get_user_by_id(user_id: str):
        sm = get_session_manager()

        async with sm.context_manager as session:
            local_conn = await get_public_local_conn_by_user_id(session, user_id)

            if not local_conn:
                raise ValueError("User not found")

            return local_conn
