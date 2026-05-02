import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.prompt import router as prompt_router
from app.config import SettingsError, require_settings
from app.errors import ConfigurationError, app_error_response
from app.graph.builder import get_portfolio_graph
from app.logging_config import configure_logging
from app.services.rate_limit import (
    ActiveStreamRegistry,
    configure_rate_limiter,
)
from app.services.session_store import InMemorySessionStore


logger = logging.getLogger("app.main")
APP_TITLE = "Portfolio Assistant"


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_portfolio_graph()
    logger.info("portfolio graph initialized at startup")
    yield


def create_app() -> FastAPI:
    try:
        settings = require_settings()
    except SettingsError as exc:
        configure_logging("ERROR", use_color=True, force=True, log_format="text")
        logger.error(str(exc))
        return _create_configuration_error_app(str(exc))

    configure_logging(settings.log_level, use_color=settings.log_color, log_format=settings.log_format)
    try:
        configure_rate_limiter(
            enabled=settings.rate_limit_enabled,
            prompt_rate_limit=settings.prompt_rate_limit,
            prompt_stream_rate_limit=settings.prompt_stream_rate_limit,
        )
    except ValueError as exc:
        logger.error("Invalid rate limit configuration: %s", exc)
        return _create_configuration_error_app(
            "Invalid application configuration. Invalid rate limit setting. Update .env and restart the application."
        )
    app = FastAPI(title=APP_TITLE, lifespan=lifespan)
    app.state.session_store = InMemorySessionStore(
        max_history_turns=settings.session_history_max_turns,
        ttl_minutes=settings.session_ttl_minutes,
    )
    app.state.active_stream_registry = ActiveStreamRegistry()
    app.include_router(prompt_router)

    @app.get("/")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": APP_TITLE}

    return app


def _create_configuration_error_app(message: str) -> FastAPI:
    app = FastAPI(title=APP_TITLE)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def configuration_error(_: str = "") -> JSONResponse:
        error = ConfigurationError(message)
        return JSONResponse(status_code=error.status_code, content=app_error_response(error))

    return app


app = create_app()
