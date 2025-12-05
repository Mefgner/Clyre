from crud import get_thread_by_id, get_all_user_threads, get_user_from_local_conn
from db import get_session_manager


class ThreadService:
    @staticmethod
    async def thread_from_id(thread_id: str):
        sm = get_session_manager()

        async with sm.context_manager as session:
            return await get_thread_by_id(session, thread_id)

    @staticmethod
    async def threads_from_user(user_id: str):
        sm = get_session_manager()

        async with sm.context_manager as session:
            user = await get_user_from_local_conn(session, user_id)
            threads = await get_all_user_threads(session, user.id)

            return threads
