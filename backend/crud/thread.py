import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from models import Thread


async def create_thread(session: AsyncSession, user_id: str, title: str = "New Thread") -> Thread:
    new_thread = Thread(user_id=user_id, title=title)
    session.add(new_thread)
    return new_thread


async def rename_thread(session: AsyncSession, thread: Thread, new_title: str) -> Thread | None:
    thread.title = new_title
    session.add(thread)
    return thread


async def star_thread(session: AsyncSession, thread: Thread, star: bool) -> Thread | None:
    thread.stared = int(star)
    session.add(thread)
    return thread


async def thread_to_project_connection(session: AsyncSession, thread: Thread, project_id: str | None) -> Thread:
    thread.project_id = project_id
    thread.in_project = 1 if project_id else 0
    session.add(thread)
    return thread


async def update_thread_time(session: AsyncSession, thread: Thread, utc_time: datetime.datetime | None) -> None:
    if not utc_time:
        utc_time = datetime.datetime.now(datetime.UTC)
    thread.update_time = utc_time
    session.add(thread)


async def get_thread_by_id(session: AsyncSession, thread_id: str) -> Thread | None:
    return await session.get(Thread, thread_id)
