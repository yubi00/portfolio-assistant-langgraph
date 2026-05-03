from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import Any

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


_token_usage_events: ContextVar[list[dict[str, int | str]]] = ContextVar(
    "openai_token_usage_events",
    default=[],
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
        self._record_token_usage("context_resolution", response)
        rewritten = response.text.strip()
        return rewritten or query

    async def classify_relevance(self, query: str, assistant_subject: str) -> RelevanceDecision:
        structured_model = self._chat.with_structured_output(RelevanceDecision, include_raw=True)
        response = await self._invoke_with_error_context(
            "relevance classification",
            lambda: structured_model.ainvoke(
                build_relevance_messages(query=query, assistant_subject=assistant_subject)
            ),
        )
        parsed = _extract_structured_response(response)
        self._record_token_usage("relevance_classification", _extract_raw_response(response))
        return parsed

    async def plan_retrieval(self, query: str, assistant_subject: str, intent: str | None = None) -> RetrievalPlan:
        structured_model = self._chat.with_structured_output(RetrievalPlan, include_raw=True)
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
        parsed = _extract_structured_response(response)
        self._record_token_usage("retrieval_planning", _extract_raw_response(response))
        return parsed

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
        self._record_token_usage("answer_generation", response)
        return response.text.strip()

    async def generate_suggestions(
        self,
        query: str,
        assistant_subject: str,
        portfolio_context: str,
        answer: str,
        intent: str | None = None,
    ) -> SuggestedPrompts:
        structured_model = self._chat.with_structured_output(SuggestedPrompts, include_raw=True)
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
        parsed = _extract_structured_response(response)
        self._record_token_usage("suggestion_generation", _extract_raw_response(response))
        return SuggestedPrompts(prompts=_normalize_suggestions(parsed.prompts))

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

    def consume_token_usage(self, operation: str) -> dict[str, int] | None:
        events = list(_token_usage_events.get())
        for index, event in enumerate(events):
            if event.get("operation") != operation:
                continue
            remaining = [*events[:index], *events[index + 1 :]]
            _token_usage_events.set(remaining)
            return {
                "input_tokens": int(event.get("input_tokens", 0)),
                "output_tokens": int(event.get("output_tokens", 0)),
                "total_tokens": int(event.get("total_tokens", 0)),
            }
        return None

    def _record_token_usage(self, operation: str, response: Any) -> None:
        usage = _extract_usage_metadata(response)
        if not usage:
            return
        event = {
            "operation": operation,
            "input_tokens": int(usage.get("input_tokens", 0)),
            "output_tokens": int(usage.get("output_tokens", 0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
        }
        _token_usage_events.set([*_token_usage_events.get(), event])


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


def _extract_structured_response(response: Any) -> Any:
    if isinstance(response, dict) and "parsed" in response:
        if response.get("parsing_error"):
            raise ValueError(f"Structured response parsing failed: {response['parsing_error']}")
        parsed = response.get("parsed")
        if parsed is None:
            raise ValueError("Structured response parsing returned no parsed value.")
        return parsed
    return response


def _extract_raw_response(response: Any) -> Any:
    if isinstance(response, dict) and "raw" in response:
        return response.get("raw")
    return response


def _extract_usage_metadata(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return None
    return {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }
