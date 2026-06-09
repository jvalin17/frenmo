"""Tests for password reset — token generation, validation, password update."""
import pytest
from datetime import datetime, timedelta

from app.models.user import User
from app.services.password_reset import (
    generate_reset_token,
    validate_reset_token,
    reset_password,
)


@pytest.fixture
async def user_alice(db_session):
    import bcrypt
    hashed = bcrypt.hashpw("oldpassword".encode(), bcrypt.gensalt()).decode()
    alice = User(email="alice@test.com", name="Alice", password_hash=hashed)
    db_session.add(alice)
    await db_session.commit()
    await db_session.refresh(alice)
    return alice


class TestGenerateToken:
    async def test_generates_token_for_valid_email(self, db_session, user_alice):
        token = await generate_reset_token(db_session, "alice@test.com")
        assert token is not None
        assert len(token) > 20

    async def test_returns_none_for_unknown_email(self, db_session, user_alice):
        token = await generate_reset_token(db_session, "nobody@test.com")
        assert token is None


class TestValidateToken:
    async def test_valid_token_returns_user(self, db_session, user_alice):
        token = await generate_reset_token(db_session, "alice@test.com")
        user = validate_reset_token(token)
        assert user is not None
        assert user["email"] == "alice@test.com"

    async def test_expired_token_returns_none(self, db_session, user_alice):
        token = await generate_reset_token(db_session, "alice@test.com")
        import time
        time.sleep(1)
        user = validate_reset_token(token, max_age_seconds=0)
        assert user is None

    async def test_tampered_token_returns_none(self, db_session, user_alice):
        user = validate_reset_token("totally.fake.token")
        assert user is None


class TestResetPassword:
    async def test_resets_password_with_valid_token(self, db_session, user_alice):
        import bcrypt
        token = await generate_reset_token(db_session, "alice@test.com")
        result = await reset_password(db_session, token, "newpassword123")
        assert result is True

        await db_session.refresh(user_alice)
        assert bcrypt.checkpw("newpassword123".encode(), user_alice.password_hash.encode())

    async def test_rejects_short_password(self, db_session, user_alice):
        token = await generate_reset_token(db_session, "alice@test.com")
        result = await reset_password(db_session, token, "short")
        assert result is False

    async def test_rejects_invalid_token(self, db_session, user_alice):
        result = await reset_password(db_session, "bad.token", "newpassword123")
        assert result is False
