from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: object) -> object:
    """Env vars carry lists as comma-separated strings; anything already a
    list (a default, or a value pydantic has parsed once) passes through."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CommaSeparated = Annotated[list[str], BeforeValidator(_split_csv)]


class BaseAppSettings(BaseSettings):
    """Every member reads the same `.env` and ignores keys meant for another
    member, so they all subclass this rather than repeating the config."""

    # enable_decoding=False: without it pydantic-settings JSON-decodes every
    # env value bound to a list/tuple/dict field *before* any validator runs,
    # so `CORPUS_REPOS=saleor/saleor=saleor/` dies in the source with
    # "error parsing value for field" instead of reaching _split_csv.
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", enable_decoding=False
    )


class CoreSettings(BaseAppSettings):
    database_url: str = "postgresql://ai:ai@postgres:5432/ai"

    log_level: str = "INFO"

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache: str = "/models"

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("postgresql+"):
            return self.database_url
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


core_settings = CoreSettings()
