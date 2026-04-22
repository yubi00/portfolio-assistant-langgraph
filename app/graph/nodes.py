from app.config import Settings
from app.graph.constants import NodeName, RetrievalSource
from app.graph.state import PortfolioState
from app.services.assistant import AssistantService
from app.services.retrieval import PortfolioRetrievalService, RetrievalResult


class PortfolioGraphNodes:
    """Node implementations for the Phase 1 graph.

    The class owns orchestration adapters only. LLM behavior stays in
    AssistantService so graph wiring and model calls can evolve separately.
    """

    def __init__(
        self,
        assistant_service: AssistantService,
        retrieval_service: PortfolioRetrievalService,
        settings: Settings,
    ) -> None:
        self._assistant_service = assistant_service
        self._retrieval_service = retrieval_service
        self._settings = settings

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

    async def retrieve_profile(self, state: PortfolioState) -> dict:
        if not _source_was_planned(state, RetrievalSource.PROFILE):
            return {"node_trace": [NodeName.RETRIEVE_PROFILE]}

        result = await self._retrieval_service.retrieve_profile(
            assistant_subject=state.get("assistant_subject", "the portfolio owner"),
            portfolio_context=state.get("portfolio_context", ""),
        )
        return _result_update(result, "profile_context", NodeName.RETRIEVE_PROFILE)

    async def retrieve_projects(self, state: PortfolioState) -> dict:
        if not _source_was_planned(state, RetrievalSource.PROJECTS):
            return {"node_trace": [NodeName.RETRIEVE_PROJECTS]}

        result = await self._retrieval_service.retrieve_projects()
        return _result_update(result, "project_context", NodeName.RETRIEVE_PROJECTS)

    async def retrieve_resume(self, state: PortfolioState) -> dict:
        if not _source_was_planned(state, RetrievalSource.RESUME):
            return {"node_trace": [NodeName.RETRIEVE_RESUME]}

        result = await self._retrieval_service.retrieve_resume()
        return _result_update(result, "resume_context", NodeName.RETRIEVE_RESUME)

    async def retrieve_work_history(self, state: PortfolioState) -> dict:
        if not _source_was_planned(state, RetrievalSource.WORK_HISTORY):
            return {"node_trace": [NodeName.RETRIEVE_WORK_HISTORY]}

        result = await self._retrieval_service.retrieve_work_history()
        return _result_update(result, "work_history_context", NodeName.RETRIEVE_WORK_HISTORY)

    async def retrieve_docs(self, state: PortfolioState) -> dict:
        if not _source_was_planned(state, RetrievalSource.DOCS):
            return {"node_trace": [NodeName.RETRIEVE_DOCS]}

        result = await self._retrieval_service.retrieve_docs()
        return _result_update(result, "docs_context", NodeName.RETRIEVE_DOCS)

    async def merge_normalize_context(self, state: PortfolioState) -> dict:
        sections = []
        for label, key in (
            ("profile", "profile_context"),
            ("projects", "project_context"),
            ("resume", "resume_context"),
            ("work_history", "work_history_context"),
            ("docs", "docs_context"),
            ("fallback_context", "portfolio_context"),
        ):
            content = state.get(key, "").strip()
            if content:
                sections.append(f"[{label}]\n{content}")

        merged_context = "\n\n".join(sections).strip()
        if len(merged_context) > self._settings.merged_context_max_chars:
            merged_context = merged_context[: self._settings.merged_context_max_chars].rstrip()

        return {
            "merged_context": merged_context,
            "node_trace": [NodeName.MERGE_NORMALIZE_CONTEXT],
        }

    async def generate_answer(self, state: PortfolioState) -> dict:
        answer = await self._assistant_service.generate_answer(
            query=state["rewritten_query"],
            assistant_subject=state.get("assistant_subject", "the portfolio owner"),
            portfolio_context=state.get("merged_context") or state.get("portfolio_context", ""),
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


def _source_was_planned(state: PortfolioState, source: RetrievalSource) -> bool:
    return source.value in state.get("retrieval_sources", [])


def _result_update(result: RetrievalResult, context_key: str, node_name: NodeName) -> dict:
    update = {"node_trace": [node_name]}
    if result.content:
        update[context_key] = result.content
    if result.error:
        update["retrieval_errors"] = [result.error]
    return update
