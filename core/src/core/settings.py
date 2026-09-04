from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .pricing import PRICES, Price, parse_prices


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

    # enable_decoding=False: otherwise pydantic-settings JSON-decodes every
    # env value bound to a list/dict field *before* any validator runs, so
    # `CORPUS_REPOS=saleor/saleor=saleor/` dies before reaching _split_csv.
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", enable_decoding=False
    )


class CoreSettings(BaseAppSettings):
    database_url: str = "postgresql://ai:ai@postgres:5432/ai"

    log_level: str = "INFO"

    # Overrides core.pricing.PRICES entry by entry, so a price change is a
    # deploy-time edit rather than a rebuild:
    #   MODEL_PRICES="gpt-4.1=2.00/0.50/8.00,my-model=1.0/4.0"
    model_prices: dict[str, Price] = Field(default_factory=dict, alias="MODEL_PRICES")

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache: str = "/models"

    @field_validator("model_prices", mode="before")
    @classmethod
    def _parse_prices(cls, value: object) -> object:
        return parse_prices(value) if isinstance(value, str) else value

    @property
    def prices(self) -> dict[str, Price]:
        """The built-in table with any environment overrides applied."""
        return {**PRICES, **self.model_prices}

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("postgresql+"):
            return self.database_url
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


core_settings = CoreSettings()
