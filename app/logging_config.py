import logging
import json
import sys
from datetime import datetime, timezone


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[35m",
}
GRAPH_COLORS = {
    "01 ingest": "\033[36m",
    "02 context": "\033[36m",
    "03 classify": "\033[33m",
    "04 plan": "\033[35m",
    "05 retrieve": "\033[34m",
    "06 merge": "\033[36m",
    "07 answer": "\033[32m",
    "07 intro": "\033[32m",
    "07 redirect": "\033[32m",
    "edge classify": "\033[33m",
}
RESET_COLOR = "\033[0m"


class ColorFormatter(logging.Formatter):
    def __init__(self, use_color: bool) -> None:
        super().__init__(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not self._use_color:
            return message
        color = _graph_color(record.getMessage()) or LEVEL_COLORS.get(record.levelno)
        if not color:
            return message
        return f"{color}{message}{RESET_COLOR}"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: str,
    use_color: bool = True,
    force: bool = False,
    log_format: str = "text",
) -> None:
    normalized_level = level.upper()
    log_level = getattr(logging, normalized_level, logging.INFO)
    handler = logging.StreamHandler(sys.__stderr__)
    formatter = _build_formatter(log_format, use_color)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    if force:
        root_logger.handlers.clear()
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        for existing_handler in root_logger.handlers:
            existing_handler.setFormatter(formatter)

    root_logger.setLevel(log_level)
    for noisy_logger_name in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy_logger_name).setLevel(logging.WARNING)


def _graph_color(log_message: str) -> str | None:
    for marker, color in GRAPH_COLORS.items():
        if marker in log_message:
            return color
    return None


def _build_formatter(log_format: str, use_color: bool) -> logging.Formatter:
    if log_format.lower() == "json":
        return JsonFormatter()
    return ColorFormatter(use_color=use_color and sys.stderr.isatty())
