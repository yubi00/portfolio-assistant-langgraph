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


class ConfigurationError(AppError):
    """Raised when the application cannot serve requests due to invalid configuration."""

    status_code = 503
    code = "CONFIGURATION_ERROR"
    default_message = "Invalid application configuration."


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


class UpstreamServiceError(AppError):
    """Raised when an external AI dependency fails in a recoverable way."""

    status_code = 503
    code = "UPSTREAM_SERVICE_ERROR"
    default_message = "Upstream service error."


def error_response(status: int, code: str, message: str) -> dict:
    return {
        "error": {
            "status": status,
            "code": code,
            "message": message,
        }
    }


def app_error_response(error: AppError) -> dict:
    return error_response(error.status_code, error.code, error.message)
