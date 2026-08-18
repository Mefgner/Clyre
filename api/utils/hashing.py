import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

import argon2
import jwt
from pydantic import BaseModel

from utils import timing

ph = argon2.PasswordHasher()


class TokenResult(BaseModel):
    token: str
    expires: datetime


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        ph.verify(stored_hash, password)
        return True
    except argon2.exceptions.VerifyMismatchError:
        return False


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def generate_uuid() -> str:
    return str(uuid.uuid4())


def create_jwt(
    payload: dict[str, Any], secret: str, from_: datetime, timespan: timedelta
) -> TokenResult:
    expires = timing.offset_datetime(from_, timespan)
    claims = {**payload, "exp": int(expires.timestamp())}
    tk = TokenResult(
        token=jwt.encode(
            claims,
            secret,
            algorithm="HS256",
        ),
        expires=expires,
    )
    return tk


def create_opaque_token(from_: datetime, timespan: timedelta) -> TokenResult:
    return TokenResult(
        token=secrets.token_urlsafe(32),
        expires=timing.offset_datetime(from_, timespan),
    )


def verify_jwt(token: str, secret: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, secret, algorithms=("HS256",))
        return payload
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid token") from exc


__all__ = [
    "create_jwt",
    "create_opaque_token",
    "generate_uuid",
    "hash_content",
    "hash_password",
    "verify_jwt",
    "verify_password",
]
