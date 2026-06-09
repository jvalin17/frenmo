from functools import wraps
from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer

from app.config import settings

session_serializer = URLSafeTimedSerializer(settings.secret_key)

SESSION_COOKIE_NAME = "frenmo_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 days


def set_session_cookie(response: Any, user_id: int) -> None:
    session_data = session_serializer.dumps({"user_id": user_id})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_data,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
    )


def clear_session_cookie(response: Any) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME)


def get_current_user_id(request: Request) -> int | None:
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_cookie:
        return None
    try:
        data = session_serializer.loads(session_cookie, max_age=SESSION_MAX_AGE)
        return data.get("user_id")
    except Exception:
        return None


def login_required(handler):
    @wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):
        user_id = get_current_user_id(request)
        if user_id is None:
            return RedirectResponse(url="/auth/login", status_code=303)
        request.state.user_id = user_id
        return await handler(request, *args, **kwargs)

    return wrapper
