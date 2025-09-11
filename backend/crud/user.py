import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import User
from utils import hashing


async def create_user(session: AsyncSession, username: str, password: str, email: str) -> User:
    password_hash = hashing.hash_password(password)
    new_user = User(name=username, id=hashing.create_uuid(), email=email, password_hash=password_hash)
    session.add(new_user)
    return new_user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email).limit(1))
    return result.scalars().first()
