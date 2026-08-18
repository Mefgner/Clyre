import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from crud import get_refresh_token
from services.auth import AuthService
from utils import hashing, web


@pytest.mark.asyncio
async def test_refresh_rotation_rejects_the_previous_token(session):
    auth = AuthService()
    access, refresh = await auth.register_locally(
        session, "TestUser", "Password1!", "rotate@example.com"
    )
    refresh_payload = await web.extract_refresh_token(refresh.token, session)
    stored_refresh = await get_refresh_token(session, str(refresh_payload.refresh_token_id))
    assert stored_refresh is not None
    assert stored_refresh.token_hash == hashing.hash_content(refresh.token)
    assert stored_refresh.token_hash != refresh.token
    old_payload = refresh_payload
    _, next_refresh = await auth.refresh_token(session, old_payload)

    old_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access.token)
    with pytest.raises(HTTPException):
        await web.extract_access_token(old_credentials, session)

    with pytest.raises(HTTPException) as error:
        await web.extract_refresh_token(refresh.token, session)
    assert error.value.status_code == 401
    await web.extract_refresh_token(next_refresh.token, session)


@pytest.mark.asyncio
async def test_logout_revokes_access_and_refresh_tokens(session):
    auth = AuthService()
    access, refresh = await auth.register_locally(
        session, "TestUser", "Password1!", "logout@example.com"
    )
    refresh_payload = await web.extract_refresh_token(refresh.token, session)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access.token)

    await web.extract_access_token(credentials, session)
    await auth.revoke_refresh_token(session, refresh_payload)

    with pytest.raises(HTTPException) as access_error:
        await web.extract_access_token(credentials, session)
    assert access_error.value.status_code == 401

    with pytest.raises(HTTPException) as refresh_error:
        await web.extract_refresh_token(refresh.token, session)
    assert refresh_error.value.status_code == 401
