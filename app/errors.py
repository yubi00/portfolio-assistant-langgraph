class AppError(Exception):
    """Base class for API-facing application errors."""

    status_code = 500
    code = "APPLICATION_ERROR"
    default_message = "Application error."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class BadRequestError(AppError):
    """Raised when a request is invalid but the client can fix it."""

    status_code = 400
    code = "BAD_REQUEST"
    default_message = "Bad request."


class AuthConfigurationError(AppError):
    """Raised when auth is requested but auth configuration is incomplete."""

    status_code = 503
    code = "AUTH_CONFIGURATION_ERROR"
    default_message = "Authentication is not configured."


class AuthRequiredError(AppError):
    """Raised when a protected endpoint is called without a valid access token."""

    status_code = 401
    code = "AUTH_REQUIRED"
    default_message = "Authentication required."


class ConfigurationError(AppError):
    """Raised when the application cannot serve requests due to invalid configuration."""

    status_code = 503
    code = "CONFIGURATION_ERROR"
    default_message = "Invalid application configuration."


class InvalidTokenError(AppError):
    """Raised when a token is malformed, expired, or otherwise invalid."""

    status_code = 401
    code = "INVALID_TOKEN"
    default_message = "Invalid or expired token."


class OriginNotAllowedError(AppError):
    """Raised when a browser origin is not in the auth allowlist."""

    status_code = 403
    code = "ORIGIN_NOT_ALLOWED"
    default_message = "Origin is not allowed."


class RateLimitExceededError(AppError):
    """Raised when a client exceeds the configured request rate."""

    status_code = 429
    code = "RATE_LIMIT_EXCEEDED"
    default_message = "Rate limit exceeded."


class PromptProcessingError(AppError):
    """Raised when prompt processing fails unexpectedly."""

    status_code = 500
    code = "PROMPT_PROCESSING_FAILED"
    default_message = "Prompt processing failed."


class StreamConcurrencyLimitExceededError(AppError):
    """Raised when a client has too many active streaming responses."""

    status_code = 429
    code = "STREAM_CONCURRENCY_LIMIT_EXCEEDED"
    default_message = "Too many active streams."


class TurnstileVerificationError(AppError):
    """Raised when Cloudflare Turnstile verification fails."""

    status_code = 400
    code = "TURNSTILE_VERIFICATION_FAILED"
    default_message = "Human verification failed."


class UpstreamServiceError(AppError):
    """Raised when an external AI dependency fails in a recoverable way."""

    status_code = 503
    code = "UPSTREAM_SERVICE_ERROR"
    default_message = "Upstream service error."


def error_response(status: int, code: str, message: str, details: list[dict] | None = None) -> dict:
    payload = {
        "error": {
            "status": status,
            "code": code,
            "message": message,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def app_error_response(error: AppError) -> dict:
    return error_response(error.status_code, error.code, error.message)
