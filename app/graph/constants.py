from enum import StrEnum


class NodeName(StrEnum):
    INGEST_USER_MESSAGE = "ingest_user_message"
    RESOLVE_CONTEXT = "resolve_context"
    POLICY_GUARD = "policy_guard"
    CLASSIFY_RELEVANCE = "classify_relevance"
    CHECK_AMBIGUITY = "check_ambiguity"
    PLAN_RETRIEVAL = "plan_retrieval"
    RETRIEVE_PROJECTS = "retrieve_projects"
    RETRIEVE_RESUME = "retrieve_resume"
    RETRIEVE_DOCS = "retrieve_docs"
    MERGE_NORMALIZE_CONTEXT = "merge_normalize_context"
    GENERATE_ANSWER = "generate_answer"
    GENERATE_SUGGESTIONS = "generate_suggestions"
    CLARIFICATION_RESPONSE = "clarification_response"
    FRIENDLY_RESPONSE = "friendly_response"
    SAVE_MEMORY = "save_memory"


class RouteName(StrEnum):
    PORTFOLIO_QUERY = "portfolio_query"
    OFF_TOPIC = "off_topic"


class RetrievalSource(StrEnum):
    PROJECTS = "projects"
    RESUME = "resume"
    DOCS = "docs"
