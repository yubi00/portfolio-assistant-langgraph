from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.graph.constants import NodeName, RouteName
from app.graph.nodes import PortfolioGraphNodes
from app.graph.routing import route_after_relevance
from app.graph.state import PortfolioState
from app.services.assistant import AssistantService
from app.services.openai_client import OpenAIAssistantClient


def build_portfolio_graph(assistant_service: AssistantService | None = None):
    if assistant_service is None:
        assistant_service = OpenAIAssistantClient(get_settings())

    nodes = PortfolioGraphNodes(assistant_service)
    builder = StateGraph(PortfolioState)

    builder.add_node(NodeName.INGEST_USER_MESSAGE, nodes.ingest_user_message)
    builder.add_node(NodeName.RESOLVE_CONTEXT, nodes.resolve_context)
    builder.add_node(NodeName.CLASSIFY_RELEVANCE, nodes.classify_relevance)
    builder.add_node(NodeName.ASSISTANT_INTRO, nodes.assistant_intro)
    builder.add_node(NodeName.GENERATE_ANSWER, nodes.generate_answer)
    builder.add_node(NodeName.FRIENDLY_RESPONSE, nodes.friendly_response)

    builder.add_edge(START, NodeName.INGEST_USER_MESSAGE)
    builder.add_edge(NodeName.INGEST_USER_MESSAGE, NodeName.RESOLVE_CONTEXT)
    builder.add_edge(NodeName.RESOLVE_CONTEXT, NodeName.CLASSIFY_RELEVANCE)
    builder.add_conditional_edges(
        NodeName.CLASSIFY_RELEVANCE,
        route_after_relevance,
        {
            RouteName.PORTFOLIO_QUERY: NodeName.GENERATE_ANSWER,
            RouteName.ASSISTANT_IDENTITY: NodeName.ASSISTANT_INTRO,
            RouteName.OFF_TOPIC: NodeName.FRIENDLY_RESPONSE,
        },
    )
    builder.add_edge(NodeName.ASSISTANT_INTRO, END)
    builder.add_edge(NodeName.GENERATE_ANSWER, END)
    builder.add_edge(NodeName.FRIENDLY_RESPONSE, END)

    return builder.compile(name="portfolio_assistant_phase_1")


@lru_cache
def get_portfolio_graph():
    return build_portfolio_graph()
