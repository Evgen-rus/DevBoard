"""Настройки DevBoard. Все секреты читаются только из окружения."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    devboard_password: str = ""
    devboard_api_token: str = ""
    devboard_secret_key: str = "dev-only-change-me"
    devboard_id_prefix: str = "DEV"
    devboard_cookie_secure: bool = False
    github_token: str = ""
    github_repo: str = ""
    storage_dir: Path = Field(default_factory=lambda: PROJECT_DIR / "storage")
    openai_api_key: str = ""
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"
    openai_transcribe_language: str = "ru"
    devboard_default_projects: str = "NeuroROP,LeadRecord,AgentBridge,NeuroHR,Other"
    devboard_skip_bootstrap: bool = False

    @property
    def api_token(self) -> str:
        return self.devboard_api_token.strip() or self.devboard_password

    @property
    def default_projects(self) -> list[str]:
        return [
            item.strip()
            for item in self.devboard_default_projects.split(",")
            if item.strip()
        ]

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token and self.github_repo and "/" in self.github_repo)

    @property
    def transcription_configured(self) -> bool:
        return bool(self.openai_api_key.strip())


def get_settings() -> Settings:
    return Settings()
