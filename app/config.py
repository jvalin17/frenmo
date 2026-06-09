import secrets

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./frenmo.db"
    secret_key: str = secrets.token_urlsafe(32)
    csrf_secret: str = secrets.token_urlsafe(32)
    debug: bool = False
    app_port: int = 8040
    resend_api_key: str = ""
    reset_from_email: str = "onboarding@resend.dev"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
