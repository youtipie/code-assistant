from __future__ import annotations

from core.settings import BaseAppSettings, CommaSeparated
from pydantic import Field


class Settings(BaseAppSettings):
    max_steps: int = Field(default=12, ge=1, le=50)
    heartbeat_seconds: int = Field(default=20, ge=1)
    turn_timeout_seconds: int = Field(default=120, ge=1)

    cors_origins: CommaSeparated = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        alias="CORS_ORIGINS",
    )


settings = Settings()
