from enum import StrEnum


class NodeName(StrEnum):
    INGEST_USER_MESSAGE = "ingest_user_message"
    RESOLVE_CONTEXT = "resolve_context"
    CLASSIFY_RELEVANCE = "classify_relevance"
    ASSISTANT_INTRO = "assistant_intro"
    GENERATE_ANSWER = "generate_answer"
    FRIENDLY_RESPONSE = "friendly_response"


class RouteName(StrEnum):
    PORTFOLIO_QUERY = "portfolio_query"
    ASSISTANT_IDENTITY = "assistant_identity"
    OFF_TOPIC = "off_topic"
