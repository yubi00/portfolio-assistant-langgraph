from app.graph.constants import NodeName
from app.graph.state import PortfolioState
from app.services.assistant import AssistantService


class PortfolioGraphNodes:
    """Node implementations for the Phase 1 graph.

    The class owns orchestration adapters only. LLM behavior stays in
    AssistantService so graph wiring and model calls can evolve separately.
    """

    def __init__(self, assistant_service: AssistantService) -> None:
        self._assistant_service = assistant_service

    async def ingest_user_message(self, state: PortfolioState) -> dict:
        user_query = state["user_query"].strip()
        if not user_query:
            raise ValueError("Prompt must not be empty.")

        return {
            "user_query": user_query,
            "rewritten_query": user_query,
            "node_trace": [NodeName.INGEST_USER_MESSAGE],
        }

    async def resolve_context(self, state: PortfolioState) -> dict:
        rewritten_query = await self._assistant_service.resolve_context(
            query=state["rewritten_query"],
            history=state.get("messages", []),
        )
        return {
            "rewritten_query": rewritten_query,
            "node_trace": [NodeName.RESOLVE_CONTEXT],
        }

    async def classify_relevance(self, state: PortfolioState) -> dict:
        decision = await self._assistant_service.classify_relevance(
            query=state["rewritten_query"],
            assistant_subject=state.get("assistant_subject", "the portfolio owner"),
        )
        return {
            "is_relevant": decision.is_relevant,
            "intent": decision.intent,
            "route": decision.route,
            "node_trace": [NodeName.CLASSIFY_RELEVANCE],
        }

    async def assistant_intro(self, state: PortfolioState) -> dict:
        answer = self._assistant_service.build_assistant_intro(
            assistant_subject=state.get("assistant_subject", "the portfolio owner")
        )
        return {
            "final_answer": answer,
            "node_trace": [NodeName.ASSISTANT_INTRO],
        }

    async def plan_retrieval(self, state: PortfolioState) -> dict:
        plan = await self._assistant_service.plan_retrieval(
            query=state["rewritten_query"],
            assistant_subject=state.get("assistant_subject", "the portfolio owner"),
            intent=state.get("intent"),
        )
        return {
            "retrieval_sources": [source.value for source in plan.sources],
            "retrieval_reason": plan.reason,
            "node_trace": [NodeName.PLAN_RETRIEVAL],
        }

    async def generate_answer(self, state: PortfolioState) -> dict:
        answer = await self._assistant_service.generate_answer(
            query=state["rewritten_query"],
            assistant_subject=state.get("assistant_subject", "the portfolio owner"),
            portfolio_context=state.get("portfolio_context", ""),
        )
        return {
            "final_answer": answer,
            "node_trace": [NodeName.GENERATE_ANSWER],
        }

    async def friendly_response(self, state: PortfolioState) -> dict:
        answer = self._assistant_service.build_friendly_response(
            assistant_subject=state.get("assistant_subject", "the portfolio owner"),
            intent=state.get("intent"),
        )
        return {
            "final_answer": answer,
            "node_trace": [NodeName.FRIENDLY_RESPONSE],
        }
