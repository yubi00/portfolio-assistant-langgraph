from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.errors import AuthRequiredError, OriginNotAllowedError
from app.services.auth_tokens import verify_access_token


def allowed_origins(settings: Settings) -> list[str]:
    return [origin.strip() for origin in settings.auth_allowed_origins.split(",") if origin.strip()]


def enforce_origin(request: Request, settings: Settings) -> None:
    origins = allowed_origins(settings)
    if not origins:
        return
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return
    if origin not in origins:
        raise OriginNotAllowedError()


def verify_prompt_authorization(request: Request, settings: Settings) -> dict | None:
    if not settings.require_auth:
        return None

    authorization = request.headers.get("authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthRequiredError()

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthRequiredError()
    return verify_access_token(settings, token)
