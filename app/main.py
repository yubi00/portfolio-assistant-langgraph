from fastapi import FastAPI

from app.api.prompt import router as prompt_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.assistant_display_name)
    app.include_router(prompt_router)

    @app.get("/")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.assistant_display_name}

    return app


app = create_app()

