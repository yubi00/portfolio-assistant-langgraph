from typing import Protocol
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field

from app.graph.constants import RetrievalSource, RouteName
from app.graph.state import ConversationTurnState


class RoutingDecision(BaseModel):
    route: RouteName = Field(description="Graph route category for the query.")
    intent: str = Field(description="Short lowercase intent label, such as projects, resume, skills, profile, or user_task.")
    sources: list[RetrievalSource] = Field(description="Portfolio data sources needed to answer the query.")
    reason: str = Field(description="Brief explanation of the selected sources; empty for off-topic queries.")


class SuggestedPrompts(BaseModel):
    prompts: list[str] = Field(
        default_factory=list,
        description="Grounded follow-up prompts the user may naturally ask next. Return at most 3.",
    )


class AssistantService(Protocol):
    async def resolve_context(self, query: str, history: list[ConversationTurnState]) -> str:
        ...

    async def classify_and_plan(self, query: str, assistant_subject: str) -> RoutingDecision:
        ...

    async def generate_answer(self, query: str, assistant_subject: str, portfolio_context: str) -> str:
        ...

    async def generate_suggestions(
        self,
        query: str,
        assistant_subject: str,
        portfolio_context: str,
        answer: str,
        intent: str | None = None,
    ) -> SuggestedPrompts:
        ...

    async def stream_answer(self, query: str, assistant_subject: str, portfolio_context: str) -> AsyncIterator[str]:
        ...

    def build_friendly_response(self, assistant_subject: str, intent: str | None = None) -> str:
        ...
