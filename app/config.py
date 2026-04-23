from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model_default: str = Field(default="gpt-4.1-mini", validation_alias="OPENAI_MODEL_DEFAULT")
    openai_temperature: float = Field(default=0.2, validation_alias="OPENAI_TEMPERATURE")

    assistant_subject: str = Field(default="the portfolio owner", validation_alias="ASSISTANT_SUBJECT")
    assistant_display_name: str = Field(default="Portfolio Assistant", validation_alias="ASSISTANT_DISPLAY_NAME")

    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_owner: str | None = Field(default=None, validation_alias="GITHUB_OWNER")
    github_api_base_url: str = Field(default="https://api.github.com", validation_alias="GITHUB_API_BASE_URL")
    github_projects_limit: int = Field(default=12, validation_alias="GITHUB_PROJECTS_LIMIT")
    github_include_forks: bool = Field(default=False, validation_alias="GITHUB_INCLUDE_FORKS")

    docs_path: str | None = Field(default=None, validation_alias="DOCS_PATH")
    merged_context_max_chars: int = Field(default=12000, validation_alias="MERGED_CONTEXT_MAX_CHARS")

    context_history_window: int = Field(default=4, validation_alias="CONTEXT_HISTORY_WINDOW")
    session_history_max_turns: int = Field(default=10, validation_alias="SESSION_HISTORY_MAX_TURNS")
    session_ttl_minutes: int = Field(default=30, validation_alias="SESSION_TTL_MINUTES")

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_color: bool = Field(default=True, validation_alias="LOG_COLOR")


@lru_cache
def get_settings() -> Settings:
    return Settings()
