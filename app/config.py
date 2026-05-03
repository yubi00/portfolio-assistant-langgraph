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
    openai_embedding_model: str = Field(default="text-embedding-3-small", validation_alias="OPENAI_EMBEDDING_MODEL")

    assistant_subject: str = Field(validation_alias="ASSISTANT_SUBJECT")

    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_owner: str | None = Field(default=None, validation_alias="GITHUB_OWNER")
    github_api_base_url: str = Field(default="https://api.github.com", validation_alias="GITHUB_API_BASE_URL")
    github_projects_limit: int = Field(default=12, validation_alias="GITHUB_PROJECTS_LIMIT")
    github_include_forks: bool = Field(default=False, validation_alias="GITHUB_INCLUDE_FORKS")
    github_readme_max_chars: int = Field(default=1800, validation_alias="GITHUB_README_MAX_CHARS")
    github_target_readme_max_chars: int = Field(default=6000, validation_alias="GITHUB_TARGET_README_MAX_CHARS")
    featured_projects_path: str = Field(default="portfolio/featured_projects.json", validation_alias="FEATURED_PROJECTS_PATH")

    docs_path: str | None = Field(default=None, validation_alias="DOCS_PATH")
    merged_context_max_chars: int = Field(default=12000, validation_alias="MERGED_CONTEXT_MAX_CHARS")

    neon_database_url_string: str | None = Field(default=None, validation_alias="NEON_DATABASE_URL_STRING")
    resume_vector_namespace: str = Field(default="default", validation_alias="RESUME_VECTOR_NAMESPACE")
    resume_chunk_max_chars: int = Field(default=1200, validation_alias="RESUME_CHUNK_MAX_CHARS")
    resume_vector_top_k: int = Field(default=5, validation_alias="RESUME_VECTOR_TOP_K")

    context_history_window: int = Field(default=4, validation_alias="CONTEXT_HISTORY_WINDOW")
    session_history_max_turns: int = Field(default=10, validation_alias="SESSION_HISTORY_MAX_TURNS")
    session_ttl_minutes: int = Field(default=30, validation_alias="SESSION_TTL_MINUTES")
    stream_chunk_buffer_chars: int = Field(default=48, validation_alias="STREAM_CHUNK_BUFFER_CHARS")

    rate_limit_enabled: bool = Field(default=True, validation_alias="RATE_LIMIT_ENABLED")
    prompt_rate_limit: str = Field(default="30/minute", validation_alias="PROMPT_RATE_LIMIT")
    prompt_stream_rate_limit: str = Field(default="10/minute", validation_alias="PROMPT_STREAM_RATE_LIMIT")
    auth_session_rate_limit: str = Field(default="3/minute", validation_alias="AUTH_SESSION_RATE_LIMIT")
    auth_token_rate_limit: str = Field(default="10/minute", validation_alias="AUTH_TOKEN_RATE_LIMIT")
    max_active_streams_per_client: int = Field(default=2, validation_alias="MAX_ACTIVE_STREAMS_PER_CLIENT")

    require_auth: bool = Field(default=False, validation_alias="REQUIRE_AUTH")
    auth_signing_secret: str | None = Field(default=None, validation_alias="AUTH_SIGNING_SECRET")
    auth_issuer: str = Field(default="portfolio-assistant-langgraph", validation_alias="AUTH_ISSUER")
    auth_audience: str = Field(default="portfolio-assistant-api", validation_alias="AUTH_AUDIENCE")
    auth_refresh_ttl_seconds: int = Field(default=1800, validation_alias="AUTH_REFRESH_TTL_SECONDS")
    auth_access_ttl_seconds: int = Field(default=60, validation_alias="AUTH_ACCESS_TTL_SECONDS")
    auth_refresh_cookie_name: str = Field(default="refresh_token", validation_alias="AUTH_REFRESH_COOKIE_NAME")
    auth_cookie_samesite: str = Field(default="none", validation_alias="AUTH_COOKIE_SAMESITE")
    auth_cookie_secure: bool = Field(default=True, validation_alias="AUTH_COOKIE_SECURE")
    auth_cookie_path: str = Field(default="/auth", validation_alias="AUTH_COOKIE_PATH")
    auth_cookie_domain: str | None = Field(default=None, validation_alias="AUTH_COOKIE_DOMAIN")
    auth_allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="AUTH_ALLOWED_ORIGINS",
    )
    turnstile_secret_key: str | None = Field(default=None, validation_alias="TURNSTILE_SECRET_KEY")
    turnstile_bypass: bool = Field(default=False, validation_alias="TURNSTILE_BYPASS")
    turnstile_verify_url: str = Field(
        default="https://challenges.cloudflare.com/turnstile/v0/siteverify",
        validation_alias="TURNSTILE_VERIFY_URL",
    )
    turnstile_timeout_seconds: float = Field(default=5.0, validation_alias="TURNSTILE_TIMEOUT_SECONDS")

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
