from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.graph.constants import NodeName, RouteName
from app.graph.nodes import PortfolioGraphNodes
from app.graph.routing import route_after_relevance
from app.graph.state import PortfolioState
from app.services.assistant import AssistantService
from app.services.openai_client import OpenAIAssistantClient
from app.services.retrieval import ConfiguredPortfolioRetrievalService, PortfolioRetrievalService


def build_portfolio_graph(
    assistant_service: AssistantService | None = None,
    retrieval_service: PortfolioRetrievalService | None = None,
):
    settings = get_settings()
    if assistant_service is None:
        assistant_service = OpenAIAssistantClient(settings)
    if retrieval_service is None:
        retrieval_service = ConfiguredPortfolioRetrievalService(settings)

    nodes = PortfolioGraphNodes(assistant_service, retrieval_service, settings)
    builder = StateGraph(PortfolioState)

    builder.add_node(NodeName.INGEST_USER_MESSAGE, nodes.ingest_user_message)
    builder.add_node(NodeName.RESOLVE_CONTEXT, nodes.resolve_context)
    builder.add_node(NodeName.CLASSIFY_RELEVANCE, nodes.classify_relevance)
    builder.add_node(NodeName.PLAN_RETRIEVAL, nodes.plan_retrieval)
    builder.add_node(NodeName.RETRIEVE_PROFILE, nodes.retrieve_profile)
    builder.add_node(NodeName.RETRIEVE_PROJECTS, nodes.retrieve_projects)
    builder.add_node(NodeName.RETRIEVE_RESUME, nodes.retrieve_resume)
    builder.add_node(NodeName.RETRIEVE_WORK_HISTORY, nodes.retrieve_work_history)
    builder.add_node(NodeName.RETRIEVE_DOCS, nodes.retrieve_docs)
    builder.add_node(NodeName.MERGE_NORMALIZE_CONTEXT, nodes.merge_normalize_context)
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
            RouteName.PORTFOLIO_QUERY: NodeName.PLAN_RETRIEVAL,
            RouteName.ASSISTANT_IDENTITY: NodeName.ASSISTANT_INTRO,
            RouteName.OFF_TOPIC: NodeName.FRIENDLY_RESPONSE,
        },
    )
    builder.add_edge(NodeName.PLAN_RETRIEVAL, NodeName.RETRIEVE_PROFILE)
    builder.add_edge(NodeName.RETRIEVE_PROFILE, NodeName.RETRIEVE_PROJECTS)
    builder.add_edge(NodeName.RETRIEVE_PROJECTS, NodeName.RETRIEVE_RESUME)
    builder.add_edge(NodeName.RETRIEVE_RESUME, NodeName.RETRIEVE_WORK_HISTORY)
    builder.add_edge(NodeName.RETRIEVE_WORK_HISTORY, NodeName.RETRIEVE_DOCS)
    builder.add_edge(NodeName.RETRIEVE_DOCS, NodeName.MERGE_NORMALIZE_CONTEXT)
    builder.add_edge(NodeName.MERGE_NORMALIZE_CONTEXT, NodeName.GENERATE_ANSWER)
    builder.add_edge(NodeName.ASSISTANT_INTRO, END)
    builder.add_edge(NodeName.GENERATE_ANSWER, END)
    builder.add_edge(NodeName.FRIENDLY_RESPONSE, END)

    return builder.compile(name="portfolio_assistant")


@lru_cache
def get_portfolio_graph():
    return build_portfolio_graph()
