from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.params import Header
from fastapi.security import HTTPAuthorizationCredentials

from schemas import general
from utils import cfg, hashing, timing


def extract_credentials(auth: Annotated[str, Header(alias="Authorization")]):
    if auth is None:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    if not auth.lower().startswith(("bearer ", "service ")):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    scheme, credentials = auth.split(" ", 1)
    return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)


def extract_access_token(
    token: Annotated[HTTPAuthorizationCredentials, Depends(extract_credentials)],
):
    if token.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    try:
        token_dict = hashing.verify_jwt(token.credentials, cfg.get_access_token_secret())

        created_at = timing.utc_from_timestamp(token_dict["timestamp"])
        expires_at = timing.offset_datetime(created_at, cfg.get_access_token_dur_minutes())
        if expires_at < timing.get_utc_now():
            raise ValueError("Access token expired")

        return general.TokenPayload(**token_dict)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc


def extract_service_token(
    token: Annotated[HTTPAuthorizationCredentials, Depends(extract_credentials)],
) -> None:
    if cfg.get_service_secret().lower() in ("forbidden", "forbiden", "", "none", None):

        raise HTTPException(status_code=403, detail="Access using service token is forbidden")
    if not token.scheme.lower() == "service":
        raise HTTPException(status_code=403, detail="Invalid authorization header")
    if not token.credentials == cfg.get_service_secret():
        raise HTTPException(status_code=403, detail="Invalid service token")
