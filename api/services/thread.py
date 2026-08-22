from sqlalchemy.ext.asyncio import AsyncSession

from crud import (
    get_all_user_threads,
    get_running_run_thread_ids,
    get_thread_by_id,
    get_user_by_id,
)
from crud.thread import delete_thread
from services.generation import active_run_thread_ids, get_run


def _mark_generating(threads, active: set[str]) -> None:
    for thread in threads:
        thread.is_generating = thread.id in active


class ThreadService:
    @staticmethod
    async def all_thread_meta(session: AsyncSession, user_id: str):
        user = await get_user_by_id(session, user_id)

        if not user:
            raise ValueError("User not found")

        threads = await get_all_user_threads(session, user.id)

        if not threads:
            raise ValueError("No threads found")

        active = active_run_thread_ids() | set(
            await get_running_run_thread_ids(session, user.id)
        )
        _mark_generating(threads, active)

        return threads

    @staticmethod
    async def thread_by_id(session, user_id: str, thread_id: str):
        user = await get_user_by_id(session, user_id)

        if not user:
            raise ValueError("User not found")

        thread = await get_thread_by_id(session, thread_id, user.id)

        if not thread:
            raise ValueError("Thread not found")

        active = active_run_thread_ids() | set(
            await get_running_run_thread_ids(session, user.id)
        )
        _mark_generating([thread], active)

        return thread

    @staticmethod
    async def delete_thread(session, user_id: str, thread_id: str):
        user = await get_user_by_id(session, user_id)

        if not user:
            raise ValueError("User not found")

        thread = await get_thread_by_id(session, thread_id, user.id)

        if not thread:
            raise ValueError("Thread not found")

        # A live generation on the thread must die with it, or its background
        # task keeps flushing into rows the cascade delete is about to remove.
        run = get_run(thread_id)
        if run is not None and not run.done:
            run.request_stop()

        await delete_thread(session, thread)

        await session.commit()
