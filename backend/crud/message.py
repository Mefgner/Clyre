from typing import Sequence
from hashlib import sha256

from sqlalchemy import select
from models import Message
from sqlalchemy.ext.asyncio import AsyncSession


async def create_message(session: AsyncSession, user_id: str, thread_id: str, role: str, content: str,
                         order: int) -> Message:
    content_hash = sha256(content.encode('utf-8')).hexdigest()
    new_message = Message(user_id=user_id, thread_id=thread_id, role=role, inline_value=content, hash=content_hash,
                          order=order)
    session.add(new_message)
    return new_message


async def get_last_message_in_thread(session: AsyncSession, thread_id: str) -> Message | None:
    last_one = await session.scalar(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.order.desc()).limit(1)
    )
    return last_one


async def get_last_message_order_in_thread(session: AsyncSession, thread_id: str) -> int:
    last_one = await get_last_message_in_thread(session, thread_id)
    return last_one.order if last_one else -1


async def get_messages_in_thread(session: AsyncSession, thread_id: str, n: int | None = None) -> Sequence[Message]:
    result = await session.execute(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.order.asc()).limit(n)
    )
    return result.scalars().all()


async def get_message_by_id(session: AsyncSession, message_id: str) -> Message | None:
    return await session.get(Message, message_id)
