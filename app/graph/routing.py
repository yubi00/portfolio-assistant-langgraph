from typing import Literal

from app.graph.constants import RouteName
from app.graph.state import PortfolioState


def route_after_relevance(state: PortfolioState) -> Literal["portfolio_query", "assistant_identity", "off_topic"]:
    route = state.get("route")
    if route == RouteName.ASSISTANT_IDENTITY:
        return RouteName.ASSISTANT_IDENTITY
    if route == RouteName.PORTFOLIO_QUERY or state.get("is_relevant"):
        return RouteName.PORTFOLIO_QUERY
    return RouteName.OFF_TOPIC
