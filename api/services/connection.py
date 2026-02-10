from sqlalchemy.ext.asyncio import AsyncSession

from crud import (
    get_local_conn_by_id,
    # get_telegram_conn_by_id,
    # get_telegram_conn_id_by_telegram_id,
    get_user_by_id,
)


class ConnectionService:
    # @staticmethod
    # async def user_from_telegram(session: AsyncSession, telegram_user_id: str, telegram_chat_id: str):
    #     conn_id = await get_telegram_conn_id_by_telegram_id(session, telegram_user_id)
    #
    #     if not conn_id:
    #         raise ValueError("Invalid credentials")
    #
    #     conn = await get_telegram_conn_by_id(session, conn_id)
    #
    #     if not conn:
    #         raise ValueError("Invalid credentials")
    #
    #     if not conn.chat_id == telegram_chat_id:
    #         raise ValueError("Invalid credentials")
    #
    #     return conn.user_id

    @staticmethod
    async def user_from_local(session: AsyncSession, local_user_id: str):
        conn = await get_local_conn_by_id(session, local_user_id)

        if not conn:
            raise ValueError("Invalid credentials")

        user = await get_user_by_id(session, conn.user_id)

        if not user:
            raise ValueError("Invalid credentials")

        return user.id
