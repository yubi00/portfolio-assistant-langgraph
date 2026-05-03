import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.errors import AppError, AuthRequiredError, RateLimitExceededError, app_error_response
from app.schemas import AuthSessionRequest, AuthSessionResponse, AuthTokenResponse
from app.services.auth import enforce_origin
from app.services.auth_cookies import get_refresh_cookie, set_refresh_cookie
from app.services.auth_tokens import mint_access_token, mint_refresh_token, verify_refresh_token
from app.services.rate_limit import client_key_from_request, rate_limit_guard
from app.services.turnstile import verify_turnstile_token

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("app.api.auth")


@router.post("/session", response_model=AuthSessionResponse)
async def create_auth_session(
    payload: AuthSessionRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthSessionResponse | JSONResponse:
    client_key = client_key_from_request(request)
    if not rate_limit_guard.hit_auth_session(client_key):
        logger.warning("auth session rejected | status=429 | client=%s | reason=rate_limit", client_key)
        return _app_error_response(RateLimitExceededError())

    try:
        enforce_origin(request, settings)
        await verify_turnstile_token(
            settings,
            response_token=payload.turnstile_token,
            remote_ip=client_key,
        )
        refresh_token, claims = mint_refresh_token(settings)
    except AppError as exc:
        logger.warning("auth session failed | status=%s | code=%s", exc.status_code, exc.code)
        return _app_error_response(exc)

    expires_in = int(claims["exp"]) - int(claims["iat"])
    response = JSONResponse(
        content=AuthSessionResponse(authenticated=True, refresh_expires_in=expires_in).model_dump()
    )
    set_refresh_cookie(response, settings, refresh_token, expires_in)
    return response


@router.post("/token", response_model=AuthTokenResponse)
async def create_access_token(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthTokenResponse | JSONResponse:
    client_key = client_key_from_request(request)
    if not rate_limit_guard.hit_auth_token(client_key):
        logger.warning("auth token rejected | status=429 | client=%s | reason=rate_limit", client_key)
        return _app_error_response(RateLimitExceededError())

    try:
        enforce_origin(request, settings)
        refresh_token = get_refresh_cookie(request, settings)
        if not refresh_token:
            raise AuthRequiredError("Refresh cookie is missing.")
        refresh_claims = verify_refresh_token(settings, refresh_token)
        access_token, access_claims = mint_access_token(settings, session_id=refresh_claims["sid"])
    except AppError as exc:
        logger.warning("auth token failed | status=%s | code=%s", exc.status_code, exc.code)
        return _app_error_response(exc)

    return AuthTokenResponse(
        access_token=access_token,
        expires_in=int(access_claims["exp"]) - int(access_claims["iat"]),
    )


def _app_error_response(error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=app_error_response(error))
