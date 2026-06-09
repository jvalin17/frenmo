import secrets

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./rupsplit.db"
    secret_key: str = secrets.token_urlsafe(32)
    csrf_secret: str = secrets.token_urlsafe(32)
    debug: bool = False
    app_port: int = 8040

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
