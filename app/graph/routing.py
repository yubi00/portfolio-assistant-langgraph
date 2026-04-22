import logging
from typing import Literal

from app.graph.constants import RouteName
from app.graph.state import PortfolioState


logger = logging.getLogger("app.graph.routing")


def route_after_relevance(state: PortfolioState) -> Literal["portfolio_query", "assistant_identity", "off_topic"]:
    route = state.get("route")
    if route == RouteName.ASSISTANT_IDENTITY:
        _log_route(RouteName.ASSISTANT_IDENTITY, state)
        return RouteName.ASSISTANT_IDENTITY
    if route == RouteName.PORTFOLIO_QUERY or state.get("is_relevant"):
        _log_route(RouteName.PORTFOLIO_QUERY, state)
        return RouteName.PORTFOLIO_QUERY
    _log_route(RouteName.OFF_TOPIC, state)
    return RouteName.OFF_TOPIC


def _log_route(route: RouteName, state: PortfolioState) -> None:
    logger.info(
        "=> %-22s | route=%s | intent=%s | relevant=%s",
        "edge classify",
        route.value,
        state.get("intent"),
        state.get("is_relevant"),
    )
