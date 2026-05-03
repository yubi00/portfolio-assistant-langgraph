import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.prompt import router as prompt_router
from app.config import SettingsError, require_settings
from app.errors import ConfigurationError, app_error_response, error_response
from app.graph.builder import get_portfolio_graph
from app.logging_config import configure_logging
from app.services.auth import allowed_origins
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
            auth_session_rate_limit=settings.auth_session_rate_limit,
            auth_token_rate_limit=settings.auth_token_rate_limit,
        )
    except ValueError as exc:
        logger.error("Invalid rate limit configuration: %s", exc)
        return _create_configuration_error_app(
            "Invalid application configuration. Invalid rate limit setting. Update .env and restart the application."
        )
    app = FastAPI(
        title=APP_TITLE,
        lifespan=lifespan,
        docs_url=None if _is_production(settings.app_env) else "/docs",
        redoc_url=None if _is_production(settings.app_env) else "/redoc",
        openapi_url=None if _is_production(settings.app_env) else "/openapi.json",
    )
    app.state.session_store = InMemorySessionStore(
        max_history_turns=settings.session_history_max_turns,
        ttl_minutes=settings.session_ttl_minutes,
    )
    app.state.active_stream_registry = ActiveStreamRegistry()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(settings),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    _register_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(prompt_router)

    @app.get("/")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": APP_TITLE}

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_response(
                422,
                "VALIDATION_ERROR",
                "Request validation failed.",
                details=_validation_error_details(exc),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        status_code = exc.status_code
        return JSONResponse(
            status_code=status_code,
            content=error_response(status_code, _http_error_code(status_code), _http_error_message(exc)),
            headers=getattr(exc, "headers", None),
        )


def _validation_error_details(exc: RequestValidationError) -> list[dict]:
    details: list[dict] = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", []) if part != "body"]
        field = ".".join(location) if location else "body"
        details.append(
            {
                "field": field,
                "message": str(error.get("msg", "Invalid input.")),
            }
        )
    return details


def _http_error_code(status_code: int) -> str:
    return {
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        429: "RATE_LIMIT_EXCEEDED",
    }.get(status_code, "HTTP_ERROR")


def _http_error_message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str) and detail:
        return detail
    return "HTTP error."


def _is_production(app_env: str) -> bool:
    return app_env.strip().lower() == "production"


def _create_configuration_error_app(message: str) -> FastAPI:
    app = FastAPI(title=APP_TITLE)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def configuration_error(_: str = "") -> JSONResponse:
        error = ConfigurationError(message)
        return JSONResponse(status_code=error.status_code, content=app_error_response(error))

    return app


app = create_app()
