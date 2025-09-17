from crud import get_telegram_conn_id_by_telegram_id, get_telegram_conn_by_id, get_local_conn_by_id, get_user_by_id
from db import get_session_manager


class ConnectionService:
    @staticmethod
    async def user_from_telegram(telegram_user_id: str, telegram_chat_id: str):
        sm = get_session_manager()

        async with sm.get_session_context_manager() as session:
            conn_id = await get_telegram_conn_id_by_telegram_id(session, telegram_user_id)

            if not conn_id:
                raise ValueError("Invalid credentials")

            conn = await get_telegram_conn_by_id(session, conn_id)

            if not conn:
                raise ValueError("Invalid credentials")

            if not conn.chat_id == telegram_chat_id:
                raise ValueError("Invalid credentials")

            return conn.user_id

    @staticmethod
    async def user_from_local(local_user_id: str):
        sm = get_session_manager()

        async with sm.get_session_context_manager() as session:
            conn = await get_local_conn_by_id(session, local_user_id)

            if not conn:
                raise ValueError("Invalid credentials")

            user = await get_user_by_id(session, conn.user_id)

            if not user:
                raise ValueError("Invalid credentials")

            return user.id
