from collections.abc import AsyncIterator

from langchain_openai import ChatOpenAI

from app.config import Settings
from app.errors import UpstreamServiceError
from app.graph.state import ConversationTurnState
from app.services.assistant import RelevanceDecision, RetrievalPlan, SuggestedPrompts
from app.services.prompt_templates import (
    build_answer_messages,
    build_context_resolution_messages,
    build_relevance_messages,
    build_retrieval_planning_messages,
    build_suggestion_messages,
)


class OpenAIAssistantClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for real LLM-backed graph execution.")

        self._settings = settings
        self._chat = ChatOpenAI(
            model=settings.openai_model_default,
            temperature=settings.openai_temperature,
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )

    async def resolve_context(self, query: str, history: list[ConversationTurnState]) -> str:
        if not history:
            return query

        recent_history = history[-self._settings.context_history_window :]
        messages = build_context_resolution_messages(query=query, history=recent_history)
        response = await self._invoke_with_error_context(
            "context resolution",
            lambda: self._chat.ainvoke(messages),
        )
        rewritten = response.text.strip()
        return rewritten or query

    async def classify_relevance(self, query: str, assistant_subject: str) -> RelevanceDecision:
        structured_model = self._chat.with_structured_output(RelevanceDecision)
        response = await self._invoke_with_error_context(
            "relevance classification",
            lambda: structured_model.ainvoke(
                build_relevance_messages(query=query, assistant_subject=assistant_subject)
            ),
        )
        return response

    async def plan_retrieval(self, query: str, assistant_subject: str, intent: str | None = None) -> RetrievalPlan:
        structured_model = self._chat.with_structured_output(RetrievalPlan)
        response = await self._invoke_with_error_context(
            "retrieval planning",
            lambda: structured_model.ainvoke(
                build_retrieval_planning_messages(
                    query=query,
                    assistant_subject=assistant_subject,
                    intent=intent,
                )
            )
        )
        return response

    async def generate_answer(self, query: str, assistant_subject: str, portfolio_context: str) -> str:
        response = await self._invoke_with_error_context(
            "answer generation",
            lambda: self._chat.ainvoke(
                build_answer_messages(
                    query=query,
                    assistant_subject=assistant_subject,
                    portfolio_context=portfolio_context,
                )
            )
        )
        return response.text.strip()

    async def generate_suggestions(
        self,
        query: str,
        assistant_subject: str,
        portfolio_context: str,
        answer: str,
        intent: str | None = None,
    ) -> SuggestedPrompts:
        structured_model = self._chat.with_structured_output(SuggestedPrompts)
        response = await self._invoke_with_error_context(
            "suggestion generation",
            lambda: structured_model.ainvoke(
                build_suggestion_messages(
                    query=query,
                    assistant_subject=assistant_subject,
                    portfolio_context=portfolio_context,
                    answer=answer,
                    intent=intent,
                )
            ),
        )
        return SuggestedPrompts(prompts=_normalize_suggestions(response.prompts))

    async def stream_answer(self, query: str, assistant_subject: str, portfolio_context: str) -> AsyncIterator[str]:
        try:
            async for chunk in self._chat.astream(
                build_answer_messages(
                    query=query,
                    assistant_subject=assistant_subject,
                    portfolio_context=portfolio_context,
                )
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            raise UpstreamServiceError("AI service failed during answer streaming.") from exc

    def build_friendly_response(self, assistant_subject: str, intent: str | None = None) -> str:
        if intent == "policy_violation":
            return (
                "I can't help with requests to override instructions, reveal hidden prompts, "
                "fabricate portfolio facts, expose secrets, or create harmful content. "
                f"I can still answer grounded questions about {assistant_subject}'s portfolio, "
                "projects, experience, skills, or professional background."
            )
        if intent == "user_task":
            return (
                "I can't debug or work on your project from here. I can help with questions about "
                f"{assistant_subject}'s portfolio, projects, experience, skills, or professional background."
            )
        return (
            f"I can help with questions about {assistant_subject}'s portfolio, projects, "
            "experience, skills, or contact details."
        )

    async def _invoke_with_error_context(self, operation: str, invoke):
        try:
            return await invoke()
        except Exception as exc:
            raise UpstreamServiceError(f"AI service failed during {operation}.") from exc


def _normalize_suggestions(prompts: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for prompt in prompts:
        clean_prompt = " ".join(prompt.split()).strip()
        if not clean_prompt:
            continue
        key = clean_prompt.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(clean_prompt)
        if len(normalized) == 3:
            break
    return normalized
