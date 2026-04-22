import operator
from typing import Annotated, NotRequired, TypedDict


class ConversationTurnState(TypedDict):
    user: str
    assistant: str


class PortfolioState(TypedDict):
    """Shared graph state.

    LangGraph nodes return partial updates to this structure. Keeping the state
    explicit makes orchestration behavior easier to inspect while learning.
    """

    user_query: str
    rewritten_query: NotRequired[str]
    messages: NotRequired[list[ConversationTurnState]]
    assistant_subject: NotRequired[str]
    portfolio_context: NotRequired[str]
    is_relevant: NotRequired[bool]
    intent: NotRequired[str]
    route: NotRequired[str]
    final_answer: NotRequired[str]
    error: NotRequired[str]
    node_trace: Annotated[list[str], operator.add]
