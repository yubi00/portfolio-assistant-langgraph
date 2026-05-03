from __future__ import annotations

import httpx

from app.config import Settings
from app.errors import AuthConfigurationError, TurnstileVerificationError


async def verify_turnstile_token(
    settings: Settings,
    *,
    response_token: str,
    remote_ip: str | None,
) -> None:
    if settings.turnstile_bypass:
        return
    if not settings.turnstile_secret_key:
        raise AuthConfigurationError("Turnstile secret key is not configured.")

    payload = {
        "secret": settings.turnstile_secret_key,
        "response": response_token,
    }
    if remote_ip and remote_ip != "unknown":
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=settings.turnstile_timeout_seconds) as client:
            response = await client.post(settings.turnstile_verify_url, data=payload)
            response.raise_for_status()
            verification = response.json()
    except httpx.HTTPError as exc:
        raise TurnstileVerificationError() from exc
    except ValueError as exc:
        raise TurnstileVerificationError() from exc

    if not isinstance(verification, dict) or not verification.get("success"):
        raise TurnstileVerificationError()
