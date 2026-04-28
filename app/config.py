from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model_default: str = Field(default="gpt-4.1-mini", validation_alias="OPENAI_MODEL_DEFAULT")
    openai_temperature: float = Field(default=0.2, validation_alias="OPENAI_TEMPERATURE")
    openai_timeout_seconds: float = Field(default=30.0, validation_alias="OPENAI_TIMEOUT_SECONDS")
    openai_max_retries: int = Field(default=2, validation_alias="OPENAI_MAX_RETRIES")

    assistant_subject: str = Field(validation_alias="ASSISTANT_SUBJECT")

    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_owner: str | None = Field(default=None, validation_alias="GITHUB_OWNER")
    github_api_base_url: str = Field(default="https://api.github.com", validation_alias="GITHUB_API_BASE_URL")
    github_projects_limit: int = Field(default=12, validation_alias="GITHUB_PROJECTS_LIMIT")
    github_include_forks: bool = Field(default=False, validation_alias="GITHUB_INCLUDE_FORKS")
    github_readme_max_chars: int = Field(default=1800, validation_alias="GITHUB_README_MAX_CHARS")
    github_target_readme_max_chars: int = Field(default=6000, validation_alias="GITHUB_TARGET_README_MAX_CHARS")

    docs_path: str | None = Field(default=None, validation_alias="DOCS_PATH")
    merged_context_max_chars: int = Field(default=12000, validation_alias="MERGED_CONTEXT_MAX_CHARS")

    context_history_window: int = Field(default=4, validation_alias="CONTEXT_HISTORY_WINDOW")
    session_history_max_turns: int = Field(default=10, validation_alias="SESSION_HISTORY_MAX_TURNS")
    session_ttl_minutes: int = Field(default=30, validation_alias="SESSION_TTL_MINUTES")
    stream_chunk_buffer_chars: int = Field(default=48, validation_alias="STREAM_CHUNK_BUFFER_CHARS")

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_color: bool = Field(default=True, validation_alias="LOG_COLOR")
    log_format: str = Field(default="text", validation_alias="LOG_FORMAT")


@lru_cache
def get_settings() -> Settings:
    return Settings()


class SettingsError(RuntimeError):
    """Raised when application settings are invalid."""


def require_settings() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        raise SettingsError(_format_settings_error(exc)) from None


def _format_settings_error(exc: ValidationError) -> str:
    missing_variables: list[str] = []
    invalid_variables: list[str] = []

    for error in exc.errors():
        location = error.get("loc", ())
        field_name = str(location[0]) if location else "unknown"
        env_name = field_name.upper()
        if error.get("type") == "missing":
            missing_variables.append(env_name)
            continue
        invalid_variables.append(f"{env_name}: {error.get('msg', 'invalid value')}")

    message_parts = ["Invalid application configuration."]
    if missing_variables:
        missing_list = ", ".join(sorted(set(missing_variables)))
        message_parts.append(f"Missing required environment variable(s): {missing_list}.")
    if invalid_variables:
        message_parts.append("Invalid setting value(s): " + "; ".join(invalid_variables) + ".")
    message_parts.append("Update .env and restart the application.")
    return " ".join(message_parts)
