import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.prompt import router as prompt_router
from app.config import SettingsError, require_settings
from app.graph.builder import get_portfolio_graph
from app.logging_config import configure_logging
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
        configure_logging("ERROR", use_color=True, force=True)
        logger.error(str(exc))
        return _create_configuration_error_app(str(exc))

    configure_logging(settings.log_level, use_color=settings.log_color)
    app = FastAPI(title=APP_TITLE, lifespan=lifespan)
    app.state.session_store = InMemorySessionStore(
        max_history_turns=settings.session_history_max_turns,
        ttl_minutes=settings.session_ttl_minutes,
    )
    app.include_router(prompt_router)

    @app.get("/")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": APP_TITLE}

    return app


def _create_configuration_error_app(message: str) -> FastAPI:
    app = FastAPI(title=APP_TITLE)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def configuration_error(_: str = "") -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": message})

    return app


app = create_app()
