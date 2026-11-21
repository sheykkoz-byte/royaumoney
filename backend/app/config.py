from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fred_api_key: str = ""
    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    twelvedata_api_key: str = ""  # optional in the cloud: the proxy injects it

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'royaumoney.db'}"
    # First date downloaded on a full backfill. Five years of z-score window
    # plus margin for 6-month changes and regime history.
    backfill_start: date = date(2000, 1, 1)

    scheduler_enabled: bool = True
    scheduler_timezone: str = "Europe/Rome"

    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
