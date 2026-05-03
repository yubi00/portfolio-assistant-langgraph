from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

from app.config import Settings
from app.errors import AuthConfigurationError, InvalidTokenError

TOKEN_ALGORITHM = "HS256"
REFRESH_TOKEN_TYPE = "refresh"
ACCESS_TOKEN_TYPE = "access"


def mint_refresh_token(settings: Settings) -> tuple[str, dict]:
    return _mint_token(settings, token_type=REFRESH_TOKEN_TYPE, ttl_seconds=settings.auth_refresh_ttl_seconds)


def mint_access_token(settings: Settings, *, session_id: str) -> tuple[str, dict]:
    return _mint_token(
        settings,
        token_type=ACCESS_TOKEN_TYPE,
        ttl_seconds=settings.auth_access_ttl_seconds,
        session_id=session_id,
    )


def verify_refresh_token(settings: Settings, token: str) -> dict:
    return _verify_token(settings, token, expected_type=REFRESH_TOKEN_TYPE)


def verify_access_token(settings: Settings, token: str) -> dict:
    return _verify_token(settings, token, expected_type=ACCESS_TOKEN_TYPE)


def _mint_token(
    settings: Settings,
    *,
    token_type: str,
    ttl_seconds: int,
    session_id: str | None = None,
) -> tuple[str, dict]:
    secret = _require_signing_secret(settings)
    if ttl_seconds <= 0:
        raise AuthConfigurationError("Authentication token TTL must be greater than zero.")

    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl_seconds)
    claims = {
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "typ": token_type,
        "sid": session_id or uuid4().hex,
        "jti": uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(claims, secret, algorithm=TOKEN_ALGORITHM)
    return token, claims


def _verify_token(settings: Settings, token: str, *, expected_type: str) -> dict:
    secret = _require_signing_secret(settings)
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[TOKEN_ALGORITHM],
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if claims.get("typ") != expected_type:
        raise InvalidTokenError()
    if not isinstance(claims.get("sid"), str) or not claims["sid"]:
        raise InvalidTokenError()
    return claims


def _require_signing_secret(settings: Settings) -> str:
    secret = settings.auth_signing_secret
    if not secret:
        raise AuthConfigurationError("Authentication signing secret is not configured.")
    if len(secret.encode("utf-8")) < 32:
        raise AuthConfigurationError("Authentication signing secret must be at least 32 bytes.")
    return secret
