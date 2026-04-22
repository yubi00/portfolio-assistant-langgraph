from typing import Protocol

from pydantic import BaseModel, Field

from app.graph.constants import RouteName
from app.graph.state import ConversationTurnState


class RelevanceDecision(BaseModel):
    route: RouteName = Field(description="Graph route category for the query.")
    is_relevant: bool = Field(description="Whether the user query should use portfolio answer generation.")
    intent: str = Field(description="Short lowercase intent label, such as projects, resume, skills, assistant_identity, or user_task.")


class AssistantService(Protocol):
    async def resolve_context(self, query: str, history: list[ConversationTurnState]) -> str:
        ...

    async def classify_relevance(self, query: str, assistant_subject: str) -> RelevanceDecision:
        ...

    async def generate_answer(self, query: str, assistant_subject: str, portfolio_context: str) -> str:
        ...

    def build_assistant_intro(self, assistant_subject: str) -> str:
        ...

    def build_friendly_response(self, assistant_subject: str, intent: str | None = None) -> str:
        ...
