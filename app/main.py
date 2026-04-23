from fastapi import FastAPI

from app.api.prompt import router as prompt_router
from app.config import get_settings
from app.logging_config import configure_logging
from app.services.session_store import InMemorySessionStore


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, use_color=settings.log_color)
    app = FastAPI(title=settings.assistant_display_name)
    app.state.session_store = InMemorySessionStore(
        max_history_turns=settings.session_history_max_turns,
        ttl_minutes=settings.session_ttl_minutes,
    )
    app.include_router(prompt_router)

    @app.get("/")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.assistant_display_name}

    return app


app = create_app()
