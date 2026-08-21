from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.params import Cookie, Header
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from crud import get_refresh_token, get_refresh_token_by_hash
from db import get_db_session
from schemas import general
from utils import cfg, env, hashing, timing


def _extract_header_credentials(authorization: Annotated[str | None, Header()] = None):
    if authorization is None:
        raise HTTPException(
            status_code=401, detail="Invalid authorization header, no credentials provided"
        )

    if not authorization.lower().startswith(("bearer ", "service ")):
        raise HTTPException(
            status_code=401, detail="Invalid authorization header, unsupported scheme"
        )

    scheme, credentials = authorization.split(" ", 1)
    return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)


async def extract_access_token(
    token: Annotated[HTTPAuthorizationCredentials, Depends(_extract_header_credentials)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    if token.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401, detail="Invalid authorization header, unsupported scheme"
        )
    try:
        token_dict = hashing.verify_jwt(token.credentials, env.ACCESS_TOKEN_SECRET)

        created_at = timing.utc_from_timestamp(token_dict["timestamp"])
        expires_at = timing.offset_datetime(created_at, cfg.get_access_token_dur_minutes())
        if expires_at < timing.get_utc_now():
            raise ValueError("Access token expired")

        payload = general.TokenPayload(**token_dict)
        _require_access_claim(payload)
        refresh_token = await get_refresh_token(session, str(payload.refresh_token_id))
        if refresh_token is None:
            raise ValueError("Refresh token is revoked or expired")
        if _refresh_token_is_invalid(refresh_token) or refresh_token.user_id != payload.user_id:
            raise ValueError("Refresh token is revoked or expired")
        return payload
    except (OverflowError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=401, detail="Invalid access token, token expired or malformed"
        ) from exc


async def extract_refresh_token(
    auth: Annotated[str, Cookie(alias="refresh_token")],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        refresh_token = await get_refresh_token_by_hash(session, hashing.hash_content(auth))
        if refresh_token is None or _refresh_token_is_invalid(refresh_token):
            raise ValueError("Refresh token is revoked or expired")
        created_at = timing.ensure_utc(refresh_token.created_at)
        return general.TokenPayload(
            user_id=refresh_token.user_id,
            timestamp=created_at.timestamp(),
            refresh_token_id=refresh_token.id,
        )
    except (OverflowError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=401, detail="Invalid refresh token, token expired or malformed"
        ) from exc


async def extract_optional_refresh_token(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[str | None, Cookie(alias="refresh_token")] = None,
):
    if auth is None:
        return None
    try:
        return await extract_refresh_token(auth, session)
    except HTTPException:
        # Logout is idempotent even if the browser presents an expired token.
        return None


def _require_access_claim(payload: general.TokenPayload) -> None:
    if not payload.refresh_token_id:
        raise ValueError("Malformed token")


def _refresh_token_is_invalid(refresh_token) -> bool:
    if not refresh_token or refresh_token.revoked_at:
        return True
    return timing.ensure_utc(refresh_token.expires_at) < timing.get_utc_now()


# def extract_service_token(
#     token: Annotated[HTTPAuthorizationCredentials, Depends(_extract_header_credentials)],
# ) -> None:
#     if env.SERVICE_SECRET.lower() in ("forbidden", "forbiden", "", "none", None):
#         raise HTTPException(status_code=403, detail="Access using service token is forbidden")
#     if token.scheme.lower() != "service":
#         raise HTTPException(
#             status_code=403, detail="Invalid authorization header, unsupported scheme"
#         )
#     if not token.credentials == env.SERVICE_SECRET:
#         raise HTTPException(status_code=403, detail="Invalid service token")
