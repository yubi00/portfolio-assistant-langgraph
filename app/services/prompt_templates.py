from functools import lru_cache
from importlib import resources

from app.graph.state import ConversationTurnState


PROMPT_PACKAGE = "app.prompts"
NO_PORTFOLIO_CONTEXT = "No portfolio context has been configured yet."


@lru_cache
def load_system_prompt(name: str) -> str:
    return resources.files(PROMPT_PACKAGE).joinpath(name).read_text(encoding="utf-8").strip()


def build_context_resolution_messages(query: str, history: list[ConversationTurnState]) -> list[tuple[str, str]]:
    history_block = "\n".join(
        f"User: {turn['user']}\nAssistant: {turn['assistant']}" for turn in history
    )
    return [
        ("system", load_system_prompt("context_resolution.md")),
        ("human", f"Conversation history:\n{history_block}\n\nLatest question:\n{query}"),
    ]


def build_relevance_messages(query: str, assistant_subject: str) -> list[tuple[str, str]]:
    return [
        ("system", load_system_prompt("relevance_classification.md")),
        ("human", f"Portfolio subject: {assistant_subject}\n\nUser query: {query}"),
    ]


def build_answer_messages(query: str, assistant_subject: str, portfolio_context: str) -> list[tuple[str, str]]:
    context = portfolio_context.strip() or NO_PORTFOLIO_CONTEXT
    return [
        ("system", load_system_prompt("answer_generation.md")),
        (
            "human",
            f"Portfolio subject: {assistant_subject}\n\nPortfolio context:\n{context}\n\nUser query: {query}",
        ),
    ]


def build_retrieval_planning_messages(query: str, assistant_subject: str, intent: str | None) -> list[tuple[str, str]]:
    intent_text = intent or "unknown"
    return [
        ("system", load_system_prompt("retrieval_planning.md")),
        (
            "human",
            f"Portfolio subject: {assistant_subject}\nIntent: {intent_text}\n\nUser query: {query}",
        ),
    ]
