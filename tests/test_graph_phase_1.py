from app.graph.builder import build_portfolio_graph
from app.graph.constants import RetrievalSource, RouteName
from app.services.assistant import RelevanceDecision, RetrievalPlan
from app.services.retrieval import RetrievalResult


class FakeAssistantService:
    async def resolve_context(self, query, history):
        return query.replace("the first one", "the first project") if history else query

    async def classify_relevance(self, query, assistant_subject):
        normalized_query = query.lower()
        if "who are you" in normalized_query:
            return RelevanceDecision(route=RouteName.ASSISTANT_IDENTITY, is_relevant=False, intent="assistant_identity")
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
        if "skill" in normalized_query:
            return RetrievalPlan(
                sources=[RetrievalSource.RESUME, RetrievalSource.PROJECTS],
                reason="Skills questions need resume facts and project evidence.",
            )
        return RetrievalPlan(
            sources=[RetrievalSource.PROJECTS],
            reason="Project questions need project data.",
        )

    def build_assistant_intro(self, assistant_subject):
        return f"I'm {assistant_subject}'s portfolio assistant."

    def build_friendly_response(self, assistant_subject, intent=None):
        if intent == "user_task":
            return f"I can't work on your project. Ask me about {assistant_subject}'s portfolio."
        return f"I can help with questions about {assistant_subject}'s portfolio."


class FakeRetrievalService:
    async def retrieve_profile(self, assistant_subject, portfolio_context):
        return RetrievalResult(source=RetrievalSource.PROFILE, content=f"Profile for {assistant_subject}")

    async def retrieve_projects(self):
        return RetrievalResult(source=RetrievalSource.PROJECTS, content="Project data")

    async def retrieve_resume(self):
        return RetrievalResult(source=RetrievalSource.RESUME, content="Resume data")

    async def retrieve_work_history(self):
        return RetrievalResult(source=RetrievalSource.WORK_HISTORY, content="Work history data")

    async def retrieve_docs(self):
        return RetrievalResult(source=RetrievalSource.DOCS, content="Docs data")


async def test_relevant_query_routes_to_generate_answer():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService())

    result = await graph.ainvoke(
        {
            "user_query": "Tell me about the first one",
            "messages": [{"user": "List projects", "assistant": "1. Example project"}],
            "assistant_subject": "Alex",
            "portfolio_context": "Alex built Example project.",
        }
    )

    assert result["is_relevant"] is True
    assert result["intent"] == "projects"
    assert result["route"] == "portfolio_query"
    assert result["retrieval_sources"] == ["projects"]
    assert result["retrieval_reason"] == "Project questions need project data."
    assert result["project_context"] == "Project data"
    assert result["merged_context"] == "[projects]\nProject data\n\n[fallback_context]\nAlex built Example project."
    assert result["rewritten_query"] == "Tell me about the first project"
    assert result["final_answer"] == "Grounded answer for Alex: Tell me about the first project"
    assert result["node_trace"] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "plan_retrieval",
        "retrieve_profile",
        "retrieve_projects",
        "retrieve_resume",
        "retrieve_work_history",
        "retrieve_docs",
        "merge_normalize_context",
        "generate_answer",
    ]


async def test_irrelevant_query_routes_to_friendly_response():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService())

    result = await graph.ainvoke(
        {
            "user_query": "What is the weather?",
            "messages": [],
            "assistant_subject": "Alex",
            "portfolio_context": "",
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
    ]


async def test_assistant_identity_routes_to_intro_response():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService())

    result = await graph.ainvoke(
        {
            "user_query": "Who are you?",
            "messages": [],
            "assistant_subject": "Alex",
            "portfolio_context": "",
        }
    )

    assert result["is_relevant"] is False
    assert result["intent"] == "assistant_identity"
    assert result["route"] == "assistant_identity"
    assert result.get("retrieval_sources") is None
    assert result["final_answer"] == "I'm Alex's portfolio assistant."
    assert result["node_trace"] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "assistant_intro",
    ]


async def test_user_project_help_routes_to_friendly_response():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService())

    result = await graph.ainvoke(
        {
            "user_query": "Can you help me fix bug in my TypeScript project?",
            "messages": [],
            "assistant_subject": "Alex",
            "portfolio_context": "",
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
    ]


async def test_skill_query_can_plan_multiple_sources():
    graph = build_portfolio_graph(FakeAssistantService(), FakeRetrievalService())

    result = await graph.ainvoke(
        {
            "user_query": "What AI skills does Alex have?",
            "messages": [],
            "assistant_subject": "Alex",
            "portfolio_context": "Alex has AI project experience.",
        }
    )

    assert result["route"] == "portfolio_query"
    assert result["retrieval_sources"] == ["resume", "projects"]
    assert result["retrieval_reason"] == "Skills questions need resume facts and project evidence."
    assert result["project_context"] == "Project data"
    assert result["resume_context"] == "Resume data"
    assert result["node_trace"] == [
        "ingest_user_message",
        "resolve_context",
        "classify_relevance",
        "plan_retrieval",
        "retrieve_profile",
        "retrieve_projects",
        "retrieve_resume",
        "retrieve_work_history",
        "retrieve_docs",
        "merge_normalize_context",
        "generate_answer",
    ]
