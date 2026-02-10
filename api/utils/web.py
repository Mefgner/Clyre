from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.params import Cookie, Header
from fastapi.security import HTTPAuthorizationCredentials

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


def extract_access_token(
    token: Annotated[HTTPAuthorizationCredentials, Depends(_extract_header_credentials)],
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

        return general.TokenPayload(**token_dict)
    except ValueError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid access token, token expired or malformed"
        ) from exc


def extract_refresh_token(
    auth: Annotated[str, Cookie(alias="refresh_token")],
):
    try:
        token_dict = hashing.verify_jwt(auth, env.REFRESH_TOKEN_SECRET)

        created_at = timing.utc_from_timestamp(token_dict["timestamp"])
        expires_at = timing.offset_datetime(created_at, cfg.get_refresh_token_dur_days())
        if expires_at < timing.get_utc_now():
            raise ValueError("Refresh token expired, generate a new one")

        return general.TokenPayload(**token_dict)
    except ValueError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid refresh token, token expired or malformed"
        ) from exc


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
