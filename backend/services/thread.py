from sqlalchemy.ext.asyncio import AsyncSession

from crud import (
    get_thread_by_id,
    get_all_user_threads,
    get_user_by_id,
)
from crud.thread import delete_thread


class ThreadService:
    @staticmethod
    async def all_thread_meta(session: AsyncSession, user_id: str):
        user = await get_user_by_id(session, user_id)

        if not user:
            raise ValueError("User not found")

        threads = await get_all_user_threads(session, user.id)

        if not threads:
            raise ValueError("No threads found")

        return threads

    @staticmethod
    async def thread_by_id(session, user_id: str, thread_id: str):
        user = await get_user_by_id(session, user_id)

        if not user:
            raise ValueError("User not found")

        thread = await get_thread_by_id(session, thread_id, user.id)

        if not thread:
            raise ValueError("Thread not found")

        return thread

    @staticmethod
    async def delete_thread(session, user_id: str, thread_id: str):
        user = await get_user_by_id(session, user_id)

        if not user:
            raise ValueError("User not found")

        thread = await get_thread_by_id(session, thread_id, user.id)

        if not thread:
            raise ValueError("Thread not found")

        await delete_thread(session, thread)

        await session.commit()
