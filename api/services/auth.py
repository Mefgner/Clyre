from sqlalchemy.ext.asyncio import AsyncSession

from crud import (
    create_local_connection,
    create_refresh_token,
    # create_telegram_connection,
    create_user,
    get_local_conn_by_email,
    get_refresh_token,
    revoke_refresh_token,
    # get_telegram_conn_by_id,
    # get_telegram_conn_id_by_telegram_id,
)
from schemas.general import TokenPayload
from utils import cfg, env, hashing, timing


class AuthService:
    @staticmethod
    def build_payload(user_id: str, timestamp: float = -1, refresh_token_id: str | None = None):
        timestamp = timestamp if timestamp != -1 else timing.get_current_timestamp()
        return TokenPayload(
            user_id=user_id, timestamp=timestamp, refresh_token_id=refresh_token_id
        )

    @staticmethod
    def generate_access_token(payload: TokenPayload):
        claims = payload.model_dump(mode="json", exclude_none=True)
        return hashing.create_jwt(
            claims,
            env.ACCESS_TOKEN_SECRET,
            timing.get_utc_now(),
            cfg.get_access_token_dur_minutes(),
        )

    @staticmethod
    def generate_refresh_token():
        return hashing.create_opaque_token(
            timing.get_utc_now(), cfg.get_refresh_token_dur_days()
        )

    async def _issue_tokens(
        self, session: AsyncSession, user_id: str, revoke_token_id: str | None = None
    ):
        refresh = self.generate_refresh_token()
        refresh_token_id = await create_refresh_token(
            session, user_id, hashing.hash_content(refresh.token), refresh.expires
        )
        payload = self.build_payload(user_id, refresh_token_id=refresh_token_id)
        access = self.generate_access_token(payload)

        if revoke_token_id and not await revoke_refresh_token(
            session, revoke_token_id, timing.get_utc_now()
        ):
            await session.rollback()
            raise ValueError("Refresh token has already been revoked")

        await session.commit()
        return access, refresh

    async def refresh_token(self, session: AsyncSession, payload: TokenPayload):
        self._require_refresh_claim(payload)
        refresh_token = await get_refresh_token(session, str(payload.refresh_token_id))
        if (
            not refresh_token
            or refresh_token.user_id != payload.user_id
            or self._is_expired(refresh_token.expires_at)
            or refresh_token.revoked_at
        ):
            raise ValueError("Invalid refresh token")
        return await self._issue_tokens(
            session, payload.user_id, revoke_token_id=str(payload.refresh_token_id)
        )

    async def register_locally(
        self,
        session: AsyncSession,
        name: str,
        password: str,
        email: str,
        user_id: str | None = None,
    ):
        lookup_existence = await get_local_conn_by_email(session, email)

        if lookup_existence:
            raise ValueError("Email already exists")

        if not user_id:
            user_id = await create_user(session)

        await create_local_connection(session, name, user_id, email, password)
        return await self._issue_tokens(session, user_id)

    async def login_locally(self, session: AsyncSession, password: str, email: str):
        conn = await get_local_conn_by_email(session, email)

        if not conn or not hashing.verify_password(conn.password_hash, password):
            raise ValueError("Invalid credentials")

        return await self._issue_tokens(session, conn.user_id)

    async def revoke_refresh_token(self, session: AsyncSession, payload: TokenPayload) -> None:
        self._require_refresh_claim(payload)
        await revoke_refresh_token(session, str(payload.refresh_token_id), timing.get_utc_now())
        await session.commit()

    @staticmethod
    def _require_refresh_claim(payload: TokenPayload) -> None:
        if not payload.refresh_token_id:
            raise ValueError("Malformed token")

    @staticmethod
    def _is_expired(expires_at):
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timing.get_utc_now().tzinfo)
        return expires_at < timing.get_utc_now()

    # @staticmethod
    # async def register_telegram(
    #     session: AsyncSession,
    #     telegram_user_id: str,
    #     telegram_chat_id: str,
    #     user_id: str | None = None,
    # ):
    #     if not user_id:
    #         user_id = await create_user(session)
    #
    #     if await get_telegram_conn_id_by_telegram_id(session, telegram_user_id):
    #         raise ValueError("Telegram account already exists")
    #
    #     await create_telegram_connection(session, telegram_user_id, user_id, telegram_chat_id)
    #
    # @staticmethod
    # async def login_telegram(session: AsyncSession, telegram_user_id: str):
    #     conn_id = await get_telegram_conn_id_by_telegram_id(session, telegram_user_id)
    #
    #     if not conn_id:
    #         raise ValueError("Invalid credentials")
    #
    #     conn = await get_telegram_conn_by_id(session, conn_id)
    #
    #     return conn.user_id
