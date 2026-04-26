import logging
from typing import Literal

from langgraph.types import Send

from app.graph.constants import NodeName, RetrievalSource, RouteName
from app.graph.state import PortfolioState


logger = logging.getLogger("app.graph.routing")


def route_after_relevance(state: PortfolioState) -> Literal["portfolio_query", "off_topic"]:
    route = state.get("route")
    if route == RouteName.PORTFOLIO_QUERY or state.get("is_relevant"):
        _log_route(RouteName.PORTFOLIO_QUERY, state)
        return RouteName.PORTFOLIO_QUERY
    _log_route(RouteName.OFF_TOPIC, state)
    return RouteName.OFF_TOPIC


def _log_route(route: RouteName, state: PortfolioState) -> None:
    request_fragment = f" | request_id={state['request_id']}" if state.get("request_id") else ""
    session_fragment = f" | session_id={state['session_id']}" if state.get("session_id") else ""
    logger.info(
        "=> %-22s | route=%s | intent=%s | relevant=%s%s%s",
        "edge classify",
        route.value,
        state.get("intent"),
        state.get("is_relevant"),
        request_fragment,
        session_fragment,
    )


def route_to_retrievers(state: PortfolioState) -> list[Send]:
    request_fragment = f" | request_id={state['request_id']}" if state.get("request_id") else ""
    session_fragment = f" | session_id={state['session_id']}" if state.get("session_id") else ""
    source_to_node = {
        RetrievalSource.PROJECTS.value: NodeName.RETRIEVE_PROJECTS,
        RetrievalSource.RESUME.value: NodeName.RETRIEVE_RESUME,
        RetrievalSource.DOCS.value: NodeName.RETRIEVE_DOCS,
    }
    sends = [
        Send(source_to_node[source], state)
        for source in state.get("retrieval_sources", [])
        if source in source_to_node
    ]
    if not sends:
        logger.warning("%-22s | no retrieval sources selected; continuing to merge", "edge retrieval")
        return [Send(NodeName.MERGE_NORMALIZE_CONTEXT, state)]

    logger.info(
        "=> %-22s | fanout=%s%s%s",
        "edge retrieval",
        ",".join(state.get("retrieval_sources", [])),
        request_fragment,
        session_fragment,
    )
    return sends
