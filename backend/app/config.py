from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_ENV = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Gateway settings loaded from environment variables or .env file."""

    remote_inference_url: str = ""
    remote_api_token: str = ""
    remote_timeout_seconds: float = 120.0
    max_concurrent_translations: int = 16

    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:80",
        "http://localhost",
    ]

    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB
    allowed_extensions: list[str] = [".txt", ".docx", ".html", ".htm"]

    result_ttl_seconds: int = 3600
    max_stored_results: int = 100

    # Rate limiting
    rate_limit_rpm: int = 20  # requests per minute per key
    rate_limit_burst: int = 5
    cookie_secret: str = "change-me-in-production"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(origin).strip() for origin in v if str(origin).strip()]
        return []

    model_config = SettingsConfigDict(
        env_file=(".env", str(_BACKEND_ENV)),
        env_file_encoding="utf-8",
        extra="ignore",
    )
