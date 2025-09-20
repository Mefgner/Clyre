from crud import (
    create_local_connection,
    create_telegram_connection,
    create_user,
    get_local_conn_by_email,
    get_telegram_conn_by_id,
    get_telegram_conn_id_by_telegram_id,
    verify_local_conn,
)
from db import get_session_manager
from schemas.general import TokenPayload
from utils import cfg, env, hashing, timing


class AuthService:
    @staticmethod
    def build_payload(user_id: str, timestamp: int = -1):
        timestamp = timestamp if timestamp != -1 else timing.get_current_timestamp()
        return TokenPayload(user_id=user_id, timestamp=timestamp)

    @staticmethod
    def generate_access_token(payload: TokenPayload):
        return hashing.create_jwt(
            payload.model_dump(),
            env.ACCESS_TOKEN_SECRET,
            timing.get_utc_now(),
            cfg.get_access_token_dur_minutes(),
        )

    @staticmethod
    def generate_refresh_token(payload: TokenPayload):
        return hashing.create_jwt(
            payload.model_dump(),
            env.REFRESH_TOKEN_SECRET,
            timing.get_utc_now(),
            cfg.get_refresh_token_dur_days(),
        )

    async def refresh_token(self, payload: TokenPayload):
        payload.timestamp = timing.get_current_timestamp()
        return self.generate_access_token(payload), self.generate_refresh_token(payload)

    async def register_locally(
        self, name: str, password: str, email: str, user_id: str | None = None
    ):
        sm = get_session_manager()

        async with sm.context_manager as session:
            lookup_existence = await get_local_conn_by_email(session, email)
            if lookup_existence:
                raise ValueError("Email already exists")

            if not user_id:
                user_id = await create_user(session)

            await create_local_connection(session, name, user_id, email, password)

        payload = self.build_payload(user_id)
        return self.generate_access_token(payload), self.generate_refresh_token(payload)

    async def login_locally(self, password: str, email: str):
        sm = get_session_manager()
        async with sm.context_manager as session:
            conn = await get_local_conn_by_email(session, email)

            if not await verify_local_conn(session, conn.id, password):
                raise ValueError("Invalid credentials")

        payload = self.build_payload(conn.user_id)
        return self.generate_access_token(payload), self.generate_refresh_token(payload)

    @staticmethod
    async def register_telegram(
        telegram_user_id: str, telegram_chat_id: str, user_id: str | None = None
    ):
        sm = get_session_manager()

        async with sm.context_manager as session:
            if not user_id:
                user_id = await create_user(session)

            if await get_telegram_conn_id_by_telegram_id(session, telegram_user_id):
                raise ValueError("Telegram account already exists")

            await create_telegram_connection(
                session, telegram_user_id, user_id, telegram_chat_id
            )

    @staticmethod
    async def login_telegram(telegram_user_id: str):
        sm = get_session_manager()

        async with sm.context_manager as session:
            conn_id = await get_telegram_conn_id_by_telegram_id(session, telegram_user_id)

            if not conn_id:
                raise ValueError("Invalid credentials")

            conn = await get_telegram_conn_by_id(session, conn_id)

            return conn.user_id
