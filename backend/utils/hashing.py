from datetime import datetime, timedelta, UTC
import hashlib
import uuid

import jwt
import argon2
from pydantic import BaseModel

ph = argon2.PasswordHasher()


class JWTToken(BaseModel):
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
    except:
        raise


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def generate_uuid() -> str:
    return str(uuid.uuid4())


def create_jwt(payload: dict[str, str], secret: str, from_: datetime, timespan: timedelta) -> JWTToken:
    expires = (from_ + timespan).now(UTC)
    tk = JWTToken(
        token=jwt.encode(payload, secret, algorithm='HS256', headers={'exp': str((from_ + timespan).now(UTC))}),
        expires=expires
    )
    return tk



def verify_jwt(token: str, secret: str) -> dict[str, str | float]:
    try:
        payload: dict[str, str | float] = jwt.decode(token, secret, algorithms=('HS256',))
        return payload
    except jwt.PyJWTError:
        raise ValueError("Invalid token")


__all__ = ["hash_password", "verify_password", "hash_content", "generate_uuid", "create_jwt", "verify_jwt"]
