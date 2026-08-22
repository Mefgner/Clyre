from collections.abc import Sequence
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Message
from utils import hashing


async def create_message(
    session: AsyncSession,
    user_id: str,
    thread_id: str,
    role: str,
    content: str,
    order: int,
    thinking: str | None = None,
) -> Message:
    content_hash = sha256(content.encode("utf-8")).hexdigest()
    new_message = Message(
        id=hashing.generate_uuid(),
        user_id=user_id,
        thread_id=thread_id,
        role=role,
        inline_value=content,
        thinking_value=thinking,
        hash=content_hash,
        order=order,
    )
    session.add(new_message)
    return new_message


async def reserve_assistant_message(
    session: AsyncSession, *, user_id: str, thread_id: str, order: int
) -> Message:
    """Create the assistant row upfront so partial content can be flushed into it."""
    new_message = Message(
        id=hashing.generate_uuid(),
        user_id=user_id,
        thread_id=thread_id,
        role="assistant",
        inline_value=None,
        hash=sha256(b"").hexdigest(),
        order=order,
    )
    session.add(new_message)
    return new_message


async def update_message_content(
    session: AsyncSession, message: Message, content: str, thinking: str | None
) -> None:
    message.inline_value = content
    message.thinking_value = thinking
    message.hash = sha256(content.encode("utf-8")).hexdigest()
    session.add(message)


async def get_last_message_in_thread(
    session: AsyncSession, thread_id: str, user_id: str
) -> Message | None:
    last_one = await session.scalar(
        select(Message)
        .where(Message.thread_id == thread_id, Message.user_id == user_id)
        .order_by(Message.order.desc())
        .limit(1)
    )
    return last_one


async def get_last_message_order_in_thread(
    session: AsyncSession, thread_id: str, user_id: str
) -> int:
    last_one = await get_last_message_in_thread(session, thread_id, user_id)
    if not last_one:
        return -1
    return last_one.order


async def get_messages_in_thread(
    session: AsyncSession, thread_id: str, user_id: str, n: int | None = None
) -> Sequence[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.thread_id == thread_id, Message.user_id == user_id)
        .order_by(Message.order.asc())
        .limit(n)
    )

    return result.scalars().all()


async def get_message_by_id(
    session: AsyncSession, message_id: str, user_id: str
) -> Message | None:
    result = await session.execute(
        select(Message).where(Message.id == message_id, Message.user_id == user_id)
    )
    return result.scalars().first()


async def delete_unwritten_assistant_rows(
    session: AsyncSession, thread_ids: Sequence[str]
) -> int:
    """Delete assistant rows their run reserved but never wrote (crash before
    the first flush). NULL inline_value marks an untouched reservation; runs
    that flushed anything wrote at least an empty string."""
    if not thread_ids:
        return 0
    result = await session.execute(
        delete(Message).where(
            Message.thread_id.in_(thread_ids),
            Message.role == "assistant",
            Message.inline_value.is_(None),
        )
    )
    return int(getattr(result, "rowcount", 0))


__all__ = [
    "create_message",
    "delete_unwritten_assistant_rows",
    "get_last_message_in_thread",
    "get_last_message_order_in_thread",
    "get_message_by_id",
    "get_messages_in_thread",
    "reserve_assistant_message",
    "update_message_content",
]
