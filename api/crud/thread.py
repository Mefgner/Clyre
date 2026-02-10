import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from models import Thread, Message
from utils import hashing


async def create_thread(
    session: AsyncSession, user_id: str, title: str = "New Thread"
) -> Thread:
    new_thread = Thread(id=hashing.generate_uuid(), user_id=user_id, title=title)
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


async def thread_to_project_connection(
    session: AsyncSession, thread: Thread, project_id: str | None
) -> Thread:
    thread.project_id = project_id
    thread.in_project = 1 if project_id else 0
    session.add(thread)
    return thread


async def update_thread_time(
    session: AsyncSession, thread: Thread, utc_time: datetime.datetime | None
) -> None:
    if not utc_time:
        utc_time = datetime.datetime.now(datetime.UTC)
    thread.update_time = utc_time
    session.add(thread)


async def get_thread_by_id(
    session: AsyncSession, thread_id: str, user_id: str, load_messages: bool = True
) -> Thread | None:
    query = select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id)
    if load_messages:
        query = (
            query.outerjoin(Thread.messages)
            .options(contains_eager(Thread.messages))
            .order_by(Message.order.asc())
        )
    res = await session.execute(query)
    return res.scalars().unique().first()


async def get_all_user_threads(
    session: AsyncSession, user_id: str, limit: int | None = None
) -> list[Thread] | None:
    query = select(Thread).where(Thread.user_id == user_id)
    if limit is not None:
        query = query.limit(limit)
    res = await session.execute(query)
    return list(res.scalars().all())


async def delete_thread(session: AsyncSession, thread: Thread) -> None:
    await session.delete(thread)


__all__ = [
    "create_thread",
    "get_thread_by_id",
    "rename_thread",
    "star_thread",
    "thread_to_project_connection",
    "update_thread_time",
    "get_all_user_threads",
]
