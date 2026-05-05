import asyncio
import logging
from collections import defaultdict

from fastapi import Request
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter


logger = logging.getLogger("app.services.rate_limit")


class RateLimitGuard:
    """Small adapter around the maintained `limits` rate-limiting library."""

    def __init__(self) -> None:
        self.configure(
            enabled=True,
            prompt_rate_limit="30/minute",
            prompt_stream_rate_limit="10/minute",
        )

    def configure(
        self,
        *,
        enabled: bool,
        prompt_rate_limit: str,
        prompt_stream_rate_limit: str,
        auth_session_rate_limit: str = "3/minute",
        auth_token_rate_limit: str = "10/minute",
    ) -> None:
        self.enabled = enabled
        self._prompt_limit = parse(prompt_rate_limit)
        self._prompt_stream_limit = parse(prompt_stream_rate_limit)
        self._auth_session_limit = parse(auth_session_rate_limit)
        self._auth_token_limit = parse(auth_token_rate_limit)
        self._storage = MemoryStorage()
        self._limiter = FixedWindowRateLimiter(self._storage)

    def hit_prompt(self, client_key: str) -> bool:
        return self._hit("prompt", client_key, self._prompt_limit)

    def hit_prompt_stream(self, client_key: str) -> bool:
        return self._hit("prompt_stream", client_key, self._prompt_stream_limit)

    def hit_auth_session(self, client_key: str) -> bool:
        return self._hit("auth_session", client_key, self._auth_session_limit)

    def hit_auth_token(self, client_key: str) -> bool:
        return self._hit("auth_token", client_key, self._auth_token_limit)

    def _hit(self, scope: str, client_key: str, limit) -> bool:
        if not self.enabled:
            return True
        return self._limiter.hit(limit, scope, client_key)


rate_limit_guard = RateLimitGuard()


def configure_rate_limiter(
    *,
    enabled: bool,
    prompt_rate_limit: str,
    prompt_stream_rate_limit: str,
    auth_session_rate_limit: str = "3/minute",
    auth_token_rate_limit: str = "10/minute",
) -> None:
    rate_limit_guard.configure(
        enabled=enabled,
        prompt_rate_limit=prompt_rate_limit,
        prompt_stream_rate_limit=prompt_stream_rate_limit,
        auth_session_rate_limit=auth_session_rate_limit,
        auth_token_rate_limit=auth_token_rate_limit,
    )


def client_key_from_request(request: Request, *, trust_proxy_headers: bool = False) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if trust_proxy_headers and forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class ActiveStreamRegistry:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def acquire(self, client_key: str, max_active_streams: int) -> bool:
        if max_active_streams <= 0:
            return True

        async with self._lock:
            if self._counts[client_key] >= max_active_streams:
                return False
            self._counts[client_key] += 1
            return True

    async def release(self, client_key: str) -> None:
        async with self._lock:
            current_count = self._counts.get(client_key, 0)
            if current_count <= 1:
                self._counts.pop(client_key, None)
                return
            self._counts[client_key] = current_count - 1

    async def active_count(self, client_key: str) -> int:
        async with self._lock:
            return self._counts.get(client_key, 0)
