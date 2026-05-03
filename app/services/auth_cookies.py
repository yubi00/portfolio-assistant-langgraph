from fastapi import Request, Response

from app.config import Settings


def set_refresh_cookie(response: Response, settings: Settings, token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=token,
        max_age=max_age_seconds,
        domain=settings.auth_cookie_domain or None,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path=settings.auth_cookie_path,
    )


def get_refresh_cookie(request: Request, settings: Settings) -> str | None:
    token = request.cookies.get(settings.auth_refresh_cookie_name)
    if not token:
        return None
    token = token.strip()
    return token or None
