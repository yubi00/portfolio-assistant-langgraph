from enum import StrEnum


class NodeName(StrEnum):
    INGEST_USER_MESSAGE = "ingest_user_message"
    RESOLVE_CONTEXT = "resolve_context"
    CLASSIFY_RELEVANCE = "classify_relevance"
    PLAN_RETRIEVAL = "plan_retrieval"
    RETRIEVE_PROFILE = "retrieve_profile"
    RETRIEVE_PROJECTS = "retrieve_projects"
    RETRIEVE_RESUME = "retrieve_resume"
    RETRIEVE_DOCS = "retrieve_docs"
    MERGE_NORMALIZE_CONTEXT = "merge_normalize_context"
    ASSISTANT_INTRO = "assistant_intro"
    GENERATE_ANSWER = "generate_answer"
    FRIENDLY_RESPONSE = "friendly_response"


class RouteName(StrEnum):
    PORTFOLIO_QUERY = "portfolio_query"
    ASSISTANT_IDENTITY = "assistant_identity"
    OFF_TOPIC = "off_topic"


class RetrievalSource(StrEnum):
    PROFILE = "profile"
    PROJECTS = "projects"
    RESUME = "resume"
    DOCS = "docs"
