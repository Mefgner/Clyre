from datetime import timedelta

import jwt
import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from services.auth import AuthService
from utils import env, hashing, timing, web


@pytest_asyncio.fixture
async def issued_tokens(session):
    return await AuthService().register_locally(
        session, "TestUser", "Password1!", "jwt-security@example.com"
    )


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _access_claims(access_token: str) -> dict:
    return hashing.verify_jwt(access_token, env.ACCESS_TOKEN_SECRET)


@pytest.mark.asyncio
async def test_valid_access_token_is_accepted(session, issued_tokens):
    access, _ = issued_tokens

    payload = await web.extract_access_token(_credentials(access.token), session)

    assert payload.user_id
    assert payload.refresh_token_id
    assert _access_claims(access.token)["exp"] > timing.get_current_timestamp()


@pytest.mark.asyncio
async def test_access_payload_tampering_is_rejected(session, issued_tokens):
    access, _ = issued_tokens
    claims = _access_claims(access.token)
    claims["user_id"] = hashing.generate_uuid()
    tampered = jwt.encode(claims, "attacker-controlled-secret", algorithm="HS256")

    with pytest.raises(HTTPException) as error:
        await web.extract_access_token(_credentials(tampered), session)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_secret_is_rejected(session, issued_tokens):
    access, _ = issued_tokens

    with pytest.raises(ValueError):
        hashing.verify_jwt(access.token, "wrong-secret")


@pytest.mark.asyncio
@pytest.mark.parametrize("algorithm", ["none", "HS512"])
async def test_unsupported_jwt_algorithms_are_rejected(session, issued_tokens, algorithm):
    access, _ = issued_tokens
    claims = _access_claims(access.token)
    secret = "" if algorithm == "none" else env.ACCESS_TOKEN_SECRET
    forged = jwt.encode(claims, secret, algorithm=algorithm)

    with pytest.raises(HTTPException) as error:
        await web.extract_access_token(_credentials(forged), session)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_access_token_is_rejected(session, issued_tokens):
    access, _ = issued_tokens
    claims = _access_claims(access.token)
    claims["exp"] = int((timing.get_utc_now() - timedelta(minutes=1)).timestamp())
    expired = jwt.encode(claims, env.ACCESS_TOKEN_SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as error:
        await web.extract_access_token(_credentials(expired), session)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_malformed_timestamp_returns_401(session, issued_tokens):
    access, _ = issued_tokens
    claims = _access_claims(access.token)
    claims["timestamp"] = "not-a-timestamp"
    malformed = jwt.encode(claims, env.ACCESS_TOKEN_SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as error:
        await web.extract_access_token(_credentials(malformed), session)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_access_token_requires_refresh_token_id(session, issued_tokens):
    access, _ = issued_tokens
    claims = _access_claims(access.token)
    claims.pop("refresh_token_id")
    malformed = jwt.encode(claims, env.ACCESS_TOKEN_SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as error:
        await web.extract_access_token(_credentials(malformed), session)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_access_token_cannot_reference_another_users_refresh_token(session):
    auth = AuthService()
    first_access, _ = await auth.register_locally(
        session, "FirstUser", "Password1!", "first-jwt@example.com"
    )
    second_access, _ = await auth.register_locally(
        session, "SecondUser", "Password1!", "second-jwt@example.com"
    )
    claims = _access_claims(first_access.token)
    claims["refresh_token_id"] = _access_claims(second_access.token)["refresh_token_id"]
    forged = jwt.encode(claims, env.ACCESS_TOKEN_SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as error:
        await web.extract_access_token(_credentials(forged), session)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_opaque_refresh_token_cannot_be_used_as_jwt(session, issued_tokens):
    _, refresh = issued_tokens

    with pytest.raises(ValueError):
        hashing.verify_jwt(refresh.token, env.ACCESS_TOKEN_SECRET)
