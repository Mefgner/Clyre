from sqlalchemy.ext.asyncio import AsyncSession

from crud import get_local_conn_by_user_id


class UserService:
    @staticmethod
    async def get_local_conn_from_internal_user(session: AsyncSession, user_id: str):
        local_conn = await get_local_conn_by_user_id(session, user_id)

        if not local_conn:
            raise ValueError("User not found")

        return local_conn
