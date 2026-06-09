import bcrypt
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

serializer = URLSafeTimedSerializer(settings.secret_key, salt="password-reset")


async def generate_reset_token(
    db: AsyncSession, email: str, expires_minutes: int = 30
) -> str | None:
    """Generate a signed reset token for the given email. Returns None if email not found."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return None

    token = serializer.dumps({"user_id": user.id, "email": user.email})
    return token


def validate_reset_token(token: str, max_age_seconds: int = 1800) -> dict | None:
    """Validate a reset token. Returns {"user_id": ..., "email": ...} or None."""
    try:
        data = serializer.loads(token, max_age=max_age_seconds)
        return data
    except (SignatureExpired, BadSignature):
        return None


async def reset_password(db: AsyncSession, token: str, new_password: str) -> bool:
    """Reset password using a valid token. Returns False if token invalid or password too short."""
    if len(new_password) < 8:
        return False

    data = validate_reset_token(token)
    if data is None:
        return False

    user = await db.get(User, data["user_id"])
    if user is None:
        return False

    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    user.password_hash = hashed
    await db.commit()
    return True
