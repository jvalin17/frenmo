from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./rupsplit.db"
    secret_key: str = "change-me-in-production"
    csrf_secret: str = "change-me-in-production"
    debug: bool = False
    app_port: int = 8040

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
