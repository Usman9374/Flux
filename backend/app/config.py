import json
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Flux API"
    app_version: str = "0.1.0"
    environment: str = "development"

    # Required. Set in backend/.env locally and in the host's env vars (Render, etc.)
    # in production. Never hardcoded — keeps secrets out of the repo.
    database_url: str = Field(..., alias="DATABASE_URL")

    # Stored as a raw string so a comma-separated env value parses cleanly.
    # Public access goes through the .cors_origins property below.
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        raw = (self.cors_origins_raw or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            value = json.loads(raw)
            if not isinstance(value, list):
                raise ValueError("CORS_ORIGINS JSON must be a list of strings.")
            return [str(item) for item in value]
        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
