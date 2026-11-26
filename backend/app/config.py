import logging
import secrets
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_ENV = Path(__file__).resolve().parent.parent / ".env"
_PLACEHOLDER_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    """Gateway settings loaded from environment variables or .env file."""

    remote_inference_url: str = ""
    remote_api_token: str = ""
    remote_timeout_seconds: float = 120.0

    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost",
    ]

    # File translation. nginx.conf must allow at least max_upload_bytes.
    max_upload_bytes: int = 3 * 1024 * 1024
    max_file_chars: int = 20_000  # each file costs GPU quota
    max_queued_jobs: int = 10
    result_ttl_seconds: int = 3600
    max_stored_results: int = 100

    # Rate limiting
    rate_limit_rpm: int = 20  # requests per minute per key
    rate_limit_burst: int = 5
    cookie_secret: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            v = v.split(",")
        return [str(origin).strip() for origin in v if str(origin).strip()]

    @field_validator("cookie_secret", mode="after")
    @classmethod
    def _never_use_a_known_secret(cls, v: str) -> str:
        if v and v != _PLACEHOLDER_SECRET:
            return v
        logging.getLogger(__name__).warning(
            "COOKIE_SECRET is not set; using a random one until restart"
        )
        return secrets.token_hex(32)

    model_config = SettingsConfigDict(
        env_file=(".env", str(_BACKEND_ENV)),
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )
