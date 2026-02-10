from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import LocalConnection, User
from utils import hashing


#
# Create
#


async def create_user(session: AsyncSession) -> str:
    """returns user id"""
    user = User(id=hashing.generate_uuid())
    session.add(user)
    return user.id


async def create_local_connection(
    session: AsyncSession, name: str, user_id: str, email: str, password: str
) -> str:
    """returns local connection id"""
    password_hash = hashing.hash_password(password)
    connection = LocalConnection(
        id=hashing.generate_uuid(),
        user_id=user_id,
        name=name,
        email=email,
        password_hash=password_hash,
    )
    session.add(connection)
    return connection.id


# async def create_telegram_connection(
#     session: AsyncSession, telegram_id: str, user_id: str, chat_id: str
# ) -> str:
#     """returns telegram connection id"""
#     connection = TelegramConnection(
#         id=hashing.generate_uuid(),
#         user_id=user_id,
#         telegram_id=telegram_id,
#         chat_id=chat_id,
#     )
#     session.add(connection)
#     return connection.id


#
# Read
#


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, user_id)


async def get_local_conn_by_id(session: AsyncSession, conn_id: str) -> LocalConnection | None:
    return await session.get(LocalConnection, conn_id)


async def get_local_conn_by_email(session: AsyncSession, email: str) -> LocalConnection | None:
    conn = await session.execute(select(LocalConnection).where(LocalConnection.email == email))
    return conn.scalars().first()


async def get_local_conn_by_user_id(
    session: AsyncSession, user_id: str
) -> LocalConnection | None:
    conn = await session.execute(
        select(LocalConnection).where(LocalConnection.user_id == user_id)
    )
    return conn.scalars().first()


# async def get_telegram_conn_by_id(
#     session: AsyncSession, conn_id: str
# ) -> TelegramConnection | None:
#     return await session.get(TelegramConnection, conn_id)
#
#
# async def get_telegram_conn_id_by_telegram_id(
#     session: AsyncSession, telegram_id: str
# ) -> str | None:
#     conn_id = await session.execute(
#         select(TelegramConnection.id).where(TelegramConnection.telegram_id == telegram_id)
#     )
#     return conn_id.scalars().first()
#


__all__ = [
    "create_local_connection",
    # "create_telegram_connection",
    "create_user",
    "get_local_conn_by_email",
    "get_local_conn_by_id",
    "get_local_conn_by_user_id",
    # "get_telegram_conn_by_id",
    # "get_telegram_conn_id_by_telegram_id",
    "get_user_by_id",
]
