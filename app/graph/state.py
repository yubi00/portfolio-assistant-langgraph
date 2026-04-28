import operator
from typing import Annotated, NotRequired, TypedDict


class ConversationTurnState(TypedDict):
    user: str
    assistant: str


class PortfolioState(TypedDict):
    """Shared graph state.

    LangGraph nodes return partial updates to this structure. Keeping the state
    explicit makes orchestration behavior easier to inspect and test.
    """

    user_query: str
    request_id: NotRequired[str]
    session_id: NotRequired[str]
    rewritten_query: NotRequired[str]
    messages: NotRequired[list[ConversationTurnState]]
    assistant_subject: NotRequired[str]
    needs_clarification: NotRequired[bool]
    clarification_question: NotRequired[str]
    portfolio_context: NotRequired[str]
    resume_path: NotRequired[str]
    docs_path: NotRequired[str]
    is_relevant: NotRequired[bool]
    intent: NotRequired[str]
    route: NotRequired[str]
    retrieval_sources: NotRequired[list[str]]
    retrieval_reason: NotRequired[str]
    project_context: NotRequired[str]
    resume_context: NotRequired[str]
    docs_context: NotRequired[str]
    merged_context: NotRequired[str]
    retrieval_errors: NotRequired[Annotated[list[str], operator.add]]
    final_answer: NotRequired[str]
    error: NotRequired[str]
    node_trace: Annotated[list[str], operator.add]
