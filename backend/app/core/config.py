
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_DATABASE_URL = (
    f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'data' / 'taskflow.db').as_posix()}"
)


class Settings(BaseSettings):
    # Application
    app_name: str = "TaskFlow AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True

    # API
    api_v1_prefix: str = "/api/v1"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e4b"
    ollama_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @field_validator("ollama_model", mode="before")
    @classmethod
    def validate_ollama_model(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("ollama_model must be a non-empty string")
        return value.strip()

    # Database
    database_url: str = DEFAULT_DATABASE_URL

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
