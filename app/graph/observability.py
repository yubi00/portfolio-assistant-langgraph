import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from time import perf_counter
from typing import Any, TypeVar

from app.graph.constants import NodeName, RetrievalSource
from app.graph.state import PortfolioState


logger = logging.getLogger("app.graph.nodes")

NodeCallable = TypeVar("NodeCallable", bound=Callable[..., Awaitable[dict[str, Any]]])
MAX_LOG_VALUE_LENGTH = 120
SKIPPED_KEY = "_log_skipped"
SKIPPED_REASON_KEY = "_log_skip_reason"

NODE_LABELS = {
    NodeName.INGEST_USER_MESSAGE: "01 ingest",
    NodeName.RESOLVE_CONTEXT: "02 context",
    NodeName.CLASSIFY_RELEVANCE: "03 classify",
    NodeName.PLAN_RETRIEVAL: "04 plan",
    NodeName.RETRIEVE_PROFILE: "05 retrieve:profile",
    NodeName.RETRIEVE_PROJECTS: "05 retrieve:projects",
    NodeName.RETRIEVE_RESUME: "05 retrieve:resume",
    NodeName.RETRIEVE_WORK_HISTORY: "05 retrieve:work",
    NodeName.RETRIEVE_DOCS: "05 retrieve:docs",
    NodeName.MERGE_NORMALIZE_CONTEXT: "06 merge",
    NodeName.GENERATE_ANSWER: "07 answer",
    NodeName.ASSISTANT_INTRO: "07 intro",
    NodeName.FRIENDLY_RESPONSE: "07 redirect",
}

RETRIEVAL_NODE_SOURCES = {
    NodeName.RETRIEVE_PROFILE: RetrievalSource.PROFILE,
    NodeName.RETRIEVE_PROJECTS: RetrievalSource.PROJECTS,
    NodeName.RETRIEVE_RESUME: RetrievalSource.RESUME,
    NodeName.RETRIEVE_WORK_HISTORY: RetrievalSource.WORK_HISTORY,
    NodeName.RETRIEVE_DOCS: RetrievalSource.DOCS,
}


def log_node(node_name: NodeName) -> Callable[[NodeCallable], NodeCallable]:
    def decorator(func: NodeCallable) -> NodeCallable:
        @wraps(func)
        async def wrapper(self: object, state: PortfolioState, *args: Any, **kwargs: Any) -> dict[str, Any]:
            started_at = perf_counter()
            label = NODE_LABELS.get(node_name, node_name.value)
            planned_source = RETRIEVAL_NODE_SOURCES.get(node_name)
            if planned_source and planned_source.value not in state.get("retrieval_sources", []):
                logger.debug("-- %-22s | skipped | source was not planned", label)
                return {"node_trace": [node_name]}

            should_start_log = logger.isEnabledFor(logging.INFO)
            if should_start_log:
                logger.info(">> %-22s | %s", label, _state_summary(state))
            try:
                update = await func(self, state, *args, **kwargs)
            except Exception:
                logger.exception("!! %-22s | error", label)
                raise

            duration_ms = (perf_counter() - started_at) * 1000
            if update.get(SKIPPED_KEY):
                if should_start_log:
                    # Keep INFO output focused on executed work; skipped retrieval nodes are DEBUG-only.
                    pass
                logger.debug(
                    "-- %-22s | skipped | %.1fms | %s",
                    label,
                    duration_ms,
                    update.get(SKIPPED_REASON_KEY, "not selected"),
                )
                return _clean_log_metadata(update)

            logger.info("<< %-22s | %.1fms | %s", label, duration_ms, _update_summary(update))
            return update

        return wrapper  # type: ignore[return-value]

    return decorator


def _state_summary(state: PortfolioState) -> str:
    route = state.get("route")
    intent = state.get("intent")
    query = state.get("rewritten_query") or state.get("user_query") or ""
    parts = [f"query={_shorten(query)!r}"]
    if route:
        parts.append(f"route={route}")
    if intent:
        parts.append(f"intent={intent}")
    if state.get("retrieval_sources"):
        parts.append(f"sources={','.join(state['retrieval_sources'])}")
    return " | ".join(parts)


def _update_summary(update: dict[str, Any]) -> str:
    visible_keys = [key for key in update if key not in {"node_trace", SKIPPED_KEY, SKIPPED_REASON_KEY}]
    if not visible_keys:
        return "node_trace"
    summary_parts = []
    for key in visible_keys:
        value = update[key]
        if isinstance(value, str):
            summary_parts.append(f"{key}={_shorten(value)!r}")
        elif isinstance(value, list):
            summary_parts.append(f"{key}=[{len(value)} item(s)]")
        else:
            summary_parts.append(f"{key}={value!r}")
    return ", ".join(summary_parts)


def _shorten(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= MAX_LOG_VALUE_LENGTH:
        return normalized
    return normalized[: MAX_LOG_VALUE_LENGTH - 3] + "..."


def skipped_update(node_name: NodeName, reason: str) -> dict[str, Any]:
    return {
        "node_trace": [node_name],
        SKIPPED_KEY: True,
        SKIPPED_REASON_KEY: reason,
    }


def _clean_log_metadata(update: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in update.items() if key not in {SKIPPED_KEY, SKIPPED_REASON_KEY}}
