from app.config import Settings
from app.graph.builder import build_portfolio_graph
from app.graph.constants import RetrievalSource, RouteName
from app.services.assistant import RelevanceDecision, RetrievalPlan
from app.services.retrieval import RetrievalResult
import logging


def _test_settings() -> Settings:
    return Settings(_env_file=None, OPENAI_API_KEY="test", ASSISTANT_SUBJECT="Alex")


class FakeAssistantService:
    async def resolve_context(self, query, history):
        if not history:
            return query
        if "third project you mentioned" in query.lower():
            return (
                "Can you provide more details about the third project you mentioned, "
                "the AI-powered audio match analysis tool for the Premier League?"
            )
        return (
            query.replace("the first one", "the first project")
            .replace("this project", "the matchcast project")
        )

    async def classify_relevance(self, query, assistant_subject):
        normalized_query = query.lower()
        if "who are you" in normalized_query:
            return RelevanceDecision(route=RouteName.PORTFOLIO_QUERY, is_relevant=True, intent="profile")
        if "fix bug" in normalized_query:
            return RelevanceDecision(route=RouteName.OFF_TOPIC, is_relevant=False, intent="user_task")
        is_relevant = "project" in normalized_query or "skill" in normalized_query
        return RelevanceDecision(
            route=RouteName.PORTFOLIO_QUERY if is_relevant else RouteName.OFF_TOPIC,
            is_relevant=is_relevant,
            intent="projects" if is_relevant else "off_topic",
        )

    async def generate_answer(self, query, assistant_subject, portfolio_context):
        return f"Grounded answer for {assistant_subject}: {query}"

    async def plan_retrieval(self, query, assistant_subject, intent=None):
        normalized_query = query.lower()
        if "who are you" in normalized_query:
            return RetrievalPlan(
                sources=[RetrievalSource.RESUME],
                reason="Profile questions should use resume grounding.",
            )
        if "skill" in normalized_query:
            return RetrievalPlan(
                sources=[RetrievalSource.RESUME, RetrievalSource.PROJECTS],
                reason="Skills questions need resume facts and project evidence.",
            )
        return RetrievalPlan(
            sources=[RetrievalSource.PROJECTS],
            reason="Project questions need project data.",
        )

    def build_friendly_response(self, assistant_subject, intent=None):
        if intent == "user_task":
            return f"I can't work on your project. Ask me about {assistant_subject}'s portfolio."
        return f"I can help with questions about {assistant_subject}'s portfolio."


class FakeRetrievalService:
    async def retrieve_projects(self, query=None):
        return RetrievalResult(source=RetrievalSource.PROJECTS, content="Project data")

    async def retrieve_resume(self, path_override=None, query=None):
        return RetrievalResult(source=RetrievalSource.RESUME, content="Resume data")

    async def retrieve_docs(self, path_override=None):
        return RetrievalResult(source=RetrievalSource.DOCS, content="Docs data")


async def test_relevant_query_routes_to_generate_answer():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService(), settings=_test_settings())

    result = await graph.ainvoke(
        {
            "user_query": "Tell me about the first one",
            "messages": [{"user": "List projects", "assistant": "1. Example project"}],
            "assistant_subject": "Alex",
        }
    )

    assert result["is_relevant"] is True
    assert result["intent"] == "projects"
    assert result["route"] == "portfolio_query"
    assert result["retrieval_sources"] == ["projects"]
    assert result["retrieval_reason"] == "Project questions need project data."
    assert result["project_context"] == "Project data"
    assert result["merged_context"] == "[projects]\nProject data"
    assert result["rewritten_query"] == "Tell me about the first project"
    assert result["final_answer"] == "Grounded answer for Alex: Tell me about the first project"
    assert result["messages"] == [
        {"user": "List projects", "assistant": "1. Example project"},
        {"user": "Tell me about the first one", "assistant": "Grounded answer for Alex: Tell me about the first project"},
    ]
    assert result["node_trace"] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "check_ambiguity",
        "plan_retrieval",
        "retrieve_projects",
        "merge_normalize_context",
        "generate_answer",
        "save_memory",
    ]


async def test_context_resolution_handles_this_project_follow_up():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService(), settings=_test_settings())

    result = await graph.ainvoke(
        {
            "user_query": "How did you deploy this project?",
            "messages": [
                {
                    "user": "Tell me about matchcast",
                    "assistant": "matchcast is an AI-powered audio match analysis project.",
                }
            ],
            "assistant_subject": "Alex",
        }
    )

    assert result["rewritten_query"] == "How did you deploy the matchcast project?"
    assert result["route"] == "portfolio_query"
    assert result["retrieval_sources"] == ["projects"]
    assert result["final_answer"] == "Grounded answer for Alex: How did you deploy the matchcast project?"
    assert result["messages"][-1] == {
        "user": "How did you deploy this project?",
        "assistant": "Grounded answer for Alex: How did you deploy the matchcast project?",
    }
    assert result["node_trace"][:4] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "check_ambiguity",
    ]


async def test_irrelevant_query_routes_to_friendly_response():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService(), settings=_test_settings())

    result = await graph.ainvoke(
        {
            "user_query": "What is the weather?",
            "messages": [],
            "assistant_subject": "Alex",
        }
    )

    assert result["is_relevant"] is False
    assert result["intent"] == "off_topic"
    assert result["route"] == "off_topic"
    assert result.get("retrieval_sources") is None
    assert result["final_answer"] == "I can help with questions about Alex's portfolio."
    assert result["node_trace"] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "friendly_response",
        "save_memory",
    ]


async def test_identity_query_routes_through_resume_retrieval():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService(), settings=_test_settings())

    result = await graph.ainvoke(
        {
            "user_query": "Who are you?",
            "messages": [],
            "assistant_subject": "Alex",
        }
    )

    assert result["is_relevant"] is True
    assert result["intent"] == "profile"
    assert result["route"] == "portfolio_query"
    assert result["retrieval_sources"] == ["resume"]
    assert result["resume_context"] == "Resume data"
    assert result["final_answer"] == "Grounded answer for Alex: Who are you?"
    assert result["node_trace"] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "check_ambiguity",
        "plan_retrieval",
        "retrieve_resume",
        "merge_normalize_context",
        "generate_answer",
        "save_memory",
    ]


async def test_user_project_help_routes_to_friendly_response():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService(), settings=_test_settings())

    result = await graph.ainvoke(
        {
            "user_query": "Can you help me fix bug in my TypeScript project?",
            "messages": [],
            "assistant_subject": "Alex",
        }
    )

    assert result["is_relevant"] is False
    assert result["intent"] == "user_task"
    assert result["route"] == "off_topic"
    assert result.get("retrieval_sources") is None
    assert result["final_answer"] == "I can't work on your project. Ask me about Alex's portfolio."
    assert result["node_trace"] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "friendly_response",
        "save_memory",
    ]


async def test_skill_query_can_plan_multiple_sources():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService(), settings=_test_settings())

    result = await graph.ainvoke(
        {
            "user_query": "What AI skills does Alex have?",
            "messages": [],
            "assistant_subject": "Alex",
        }
    )

    assert result["route"] == "portfolio_query"
    assert result["retrieval_sources"] == ["resume", "projects"]
    assert result["retrieval_reason"] == "Skills questions need resume facts and project evidence."
    assert result["project_context"] == "Project data"
    assert result["resume_context"] == "Resume data"
    assert result["node_trace"][:4] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "check_ambiguity",
    ]
    assert result["node_trace"][4] == "plan_retrieval"
    assert "retrieve_projects" in result["node_trace"]
    assert "retrieve_resume" in result["node_trace"]
    assert "retrieve_docs" not in result["node_trace"]
    assert result["node_trace"][-3:] == ["merge_normalize_context", "generate_answer", "save_memory"]


async def test_ambiguous_project_reference_returns_clarification():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService(), settings=_test_settings())

    result = await graph.ainvoke(
        {
            "user_query": "Tell me more about the second project",
            "messages": [
                {
                    "user": "What projects has Alex built?",
                    "assistant": "1. **matchcast**\n2. **ai-portfolio-voice-service**",
                }
            ],
            "assistant_subject": "Alex",
        }
    )

    assert result["needs_clarification"] is True
    assert (
        result["final_answer"]
        == "Which project do you mean: matchcast or ai-portfolio-voice-service?"
    )
    assert result.get("retrieval_sources") is None
    assert result["node_trace"] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "check_ambiguity",
        "clarification_response",
        "save_memory",
    ]
    assert result["messages"][-1] == {
        "user": "Tell me more about the second project",
        "assistant": "Which project do you mean: matchcast or ai-portfolio-voice-service?",
    }


async def test_descriptive_rewritten_query_skips_unnecessary_clarification():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService(), settings=_test_settings())

    result = await graph.ainvoke(
        {
            "user_query": "Tell me more about the third project you mentioned?",
            "messages": [
                {
                    "user": "What projects has Alex built?",
                    "assistant": (
                        "1. **ai-portfolio-voice-service**\n"
                        "- A 1:1 audio conversation system with an AI version of me.\n"
                        "2. **ai-portfolio**\n"
                        "- A terminal-style AI portfolio website.\n"
                        "3. **matchcast**\n"
                        "- An AI-powered audio match analysis tool for the Premier League."
                    ),
                }
            ],
            "assistant_subject": "Alex",
        }
    )

    assert result["needs_clarification"] is False
    assert result["retrieval_sources"] == ["projects"]
    assert result["final_answer"].startswith("Grounded answer for Alex:")
    assert "clarification_response" not in result["node_trace"]


async def test_graph_logs_include_request_id(caplog):
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService(), settings=_test_settings())

    with caplog.at_level(logging.INFO):
        result = await graph.ainvoke(
            {
                "user_query": "Tell me about the first one",
                "messages": [{"user": "List projects", "assistant": "1. Example project"}],
                "assistant_subject": "Alex",
                "request_id": "req-123",
                "session_id": "session-123",
            }
        )

    assert result["route"] == "portfolio_query"
    assert "request_id=req-123" in caplog.text
    assert "session_id=session-123" in caplog.text
