"""Tests for session cookie security — no persistent cookie, logout on close."""
from unittest.mock import MagicMock

from app.middleware.auth import set_session_cookie


class TestSessionCookieIsBrowserScoped:
    """Session cookie must not persist across browser restarts."""

    def test_set_session_cookie_has_no_max_age(self):
        """Cookie without max_age is a session cookie — deleted when browser closes."""
        response = MagicMock()
        set_session_cookie(response, user_id=42)

        response.set_cookie.assert_called_once()
        call_kwargs = response.set_cookie.call_args[1]

        # max_age must not be set (or be None) — browser session cookie
        assert call_kwargs.get("max_age") is None, (
            f"Cookie has max_age={call_kwargs['max_age']} — it will persist across browser restarts"
        )

    def test_set_session_cookie_is_httponly(self):
        """Cookie must be httponly to prevent XSS theft."""
        response = MagicMock()
        set_session_cookie(response, user_id=42)

        call_kwargs = response.set_cookie.call_args[1]
        assert call_kwargs.get("httponly") is True

    def test_set_session_cookie_is_samesite_lax(self):
        """Cookie must be samesite=lax to prevent CSRF."""
        response = MagicMock()
        set_session_cookie(response, user_id=42)

        call_kwargs = response.set_cookie.call_args[1]
        assert call_kwargs.get("samesite") == "lax"
