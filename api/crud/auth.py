from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import RefreshToken
from utils import hashing


async def create_refresh_token(
    session: AsyncSession,
    user_id: str,
    token_hash: str,
    expires_at: datetime,
) -> str:
    refresh_token = RefreshToken(
        id=hashing.generate_uuid(),
        token_hash=token_hash,
        user_id=user_id,
        expires_at=expires_at,
    )
    session.add(refresh_token)
    return refresh_token.id


async def get_refresh_token(session: AsyncSession, token_id: str) -> RefreshToken | None:
    return await session.get(RefreshToken, token_id)


async def get_refresh_token_by_hash(
    session: AsyncSession, token_hash: str
) -> RefreshToken | None:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.scalars().first()


async def revoke_refresh_token(
    session: AsyncSession, token_id: str, revoked_at: datetime
) -> bool:
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == token_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=revoked_at)
    )
    return getattr(result, "rowcount", 0) == 1


__all__ = [
    "create_refresh_token",
    "get_refresh_token",
    "get_refresh_token_by_hash",
    "revoke_refresh_token",
]
