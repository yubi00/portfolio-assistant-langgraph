from typing import Protocol
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field

from app.graph.constants import RetrievalSource, RouteName
from app.graph.state import ConversationTurnState


class RelevanceDecision(BaseModel):
    route: RouteName = Field(description="Graph route category for the query.")
    is_relevant: bool = Field(description="Whether the user query should use portfolio answer generation.")
    intent: str = Field(description="Short lowercase intent label, such as projects, resume, skills, profile, or user_task.")


class RetrievalPlan(BaseModel):
    sources: list[RetrievalSource] = Field(description="Portfolio data sources needed to answer the query.")
    reason: str = Field(description="Brief explanation of why these sources are needed.")


class AssistantService(Protocol):
    async def resolve_context(self, query: str, history: list[ConversationTurnState]) -> str:
        ...

    async def classify_relevance(self, query: str, assistant_subject: str) -> RelevanceDecision:
        ...

    async def plan_retrieval(self, query: str, assistant_subject: str, intent: str | None = None) -> RetrievalPlan:
        ...

    async def generate_answer(self, query: str, assistant_subject: str, portfolio_context: str) -> str:
        ...

    async def stream_answer(self, query: str, assistant_subject: str, portfolio_context: str) -> AsyncIterator[str]:
        ...

    def build_friendly_response(self, assistant_subject: str, intent: str | None = None) -> str:
        ...
