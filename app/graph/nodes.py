import logging
import re

from app.config import Settings
from app.graph.constants import NodeName, RetrievalSource
from app.graph.observability import log_node, skipped_update
from app.graph.state import PortfolioState
from app.services.assistant import AssistantService
from app.services.retrieval import PortfolioRetrievalService, RetrievalResult


logger = logging.getLogger("app.graph.nodes")


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

    @log_node(NodeName.INGEST_USER_MESSAGE)
    async def ingest_user_message(self, state: PortfolioState) -> dict:
        user_query = state["user_query"].strip()
        if not user_query:
            raise ValueError("Prompt must not be empty.")

        return {
            "user_query": user_query,
            "rewritten_query": user_query,
            "node_trace": [NodeName.INGEST_USER_MESSAGE],
        }

    @log_node(NodeName.RESOLVE_CONTEXT)
    async def resolve_context(self, state: PortfolioState) -> dict:
        rewritten_query = await self._assistant_service.resolve_context(
            query=state["rewritten_query"],
            history=state.get("messages", []),
        )
        return {
            "rewritten_query": rewritten_query,
            "node_trace": [NodeName.RESOLVE_CONTEXT],
            **_llm_usage_update(
                self._assistant_service,
                NodeName.RESOLVE_CONTEXT,
                "context_resolution",
            ),
        }

    @log_node(NodeName.POLICY_GUARD)
    async def policy_guard(self, state: PortfolioState) -> dict:
        policy_reason = _detect_policy_violation(state["rewritten_query"])
        if policy_reason:
            return {
                "policy_violation": True,
                "policy_reason": policy_reason,
                "is_relevant": False,
                "intent": "policy_violation",
                "route": "off_topic",
                "node_trace": [NodeName.POLICY_GUARD],
            }

        return {
            "policy_violation": False,
            "node_trace": [NodeName.POLICY_GUARD],
        }

    @log_node(NodeName.CLASSIFY_RELEVANCE)
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
            **_llm_usage_update(
                self._assistant_service,
                NodeName.CLASSIFY_RELEVANCE,
                "relevance_classification",
            ),
        }

    @log_node(NodeName.CHECK_AMBIGUITY)
    async def check_ambiguity(self, state: PortfolioState) -> dict:
        candidate_entries = _extract_recent_list_candidates(state.get("messages", []))
        candidates = [entry["name"] for entry in candidate_entries]
        if not _is_ambiguous_reference(state["rewritten_query"]) or len(candidates) < 2:
            return {
                "needs_clarification": False,
                "node_trace": [NodeName.CHECK_AMBIGUITY],
            }

        if _resolve_unique_candidate_from_query(state["rewritten_query"], candidate_entries):
            return {
                "needs_clarification": False,
                "node_trace": [NodeName.CHECK_AMBIGUITY],
            }

        clarification_question = _build_clarification_question(state["rewritten_query"], candidates)
        return {
            "needs_clarification": True,
            "clarification_question": clarification_question,
            "node_trace": [NodeName.CHECK_AMBIGUITY],
        }

    @log_node(NodeName.PLAN_RETRIEVAL)
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
            **_llm_usage_update(
                self._assistant_service,
                NodeName.PLAN_RETRIEVAL,
                "retrieval_planning",
            ),
        }

    @log_node(NodeName.RETRIEVE_PROJECTS)
    async def retrieve_projects(self, state: PortfolioState) -> dict:
        if not _source_was_planned(state, RetrievalSource.PROJECTS):
            return skipped_update(NodeName.RETRIEVE_PROJECTS, "projects source was not planned")

        result = await self._retrieval_service.retrieve_projects(state.get("rewritten_query"))
        return _result_update(result, "project_context", NodeName.RETRIEVE_PROJECTS)

    @log_node(NodeName.RETRIEVE_RESUME)
    async def retrieve_resume(self, state: PortfolioState) -> dict:
        if not _source_was_planned(state, RetrievalSource.RESUME):
            return skipped_update(NodeName.RETRIEVE_RESUME, "resume source was not planned")

        result = await self._retrieval_service.retrieve_resume(
            query=state.get("rewritten_query"),
            path_override=state.get("resume_path"),
        )
        return _result_update(result, "resume_context", NodeName.RETRIEVE_RESUME)

    @log_node(NodeName.RETRIEVE_DOCS)
    async def retrieve_docs(self, state: PortfolioState) -> dict:
        if not _source_was_planned(state, RetrievalSource.DOCS):
            return skipped_update(NodeName.RETRIEVE_DOCS, "docs source was not planned")

        result = await self._retrieval_service.retrieve_docs(state.get("docs_path"))
        return _result_update(result, "docs_context", NodeName.RETRIEVE_DOCS)

    @log_node(NodeName.MERGE_NORMALIZE_CONTEXT)
    async def merge_normalize_context(self, state: PortfolioState) -> dict:
        sections = []
        for label, key in (
            ("projects", "project_context"),
            ("resume", "resume_context"),
            ("docs", "docs_context"),
            ("inline_context", "portfolio_context"),
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

    @log_node(NodeName.GENERATE_ANSWER)
    async def generate_answer(self, state: PortfolioState) -> dict:
        answer = await self._assistant_service.generate_answer(
            query=state["rewritten_query"],
            assistant_subject=state.get("assistant_subject", "the portfolio owner"),
            portfolio_context=state.get("merged_context") or state.get("portfolio_context", ""),
        )
        return {
            "final_answer": answer,
            "node_trace": [NodeName.GENERATE_ANSWER],
            **_llm_usage_update(
                self._assistant_service,
                NodeName.GENERATE_ANSWER,
                "answer_generation",
            ),
        }

    @log_node(NodeName.GENERATE_SUGGESTIONS)
    async def generate_suggestions(self, state: PortfolioState) -> dict:
        if not _should_generate_suggestions(state):
            return {
                "suggested_prompts": [],
                "node_trace": [NodeName.GENERATE_SUGGESTIONS],
            }

        try:
            suggestions = await self._assistant_service.generate_suggestions(
                query=state["rewritten_query"],
                assistant_subject=state.get("assistant_subject", "the portfolio owner"),
                portfolio_context=state.get("merged_context") or state.get("portfolio_context", ""),
                answer=state.get("final_answer", ""),
                intent=state.get("intent"),
            )
        except Exception:
            logger.warning("suggestion generation failed; continuing without suggestions", exc_info=True)
            return {
                "suggested_prompts": [],
                "node_trace": [NodeName.GENERATE_SUGGESTIONS],
            }
        return {
            "suggested_prompts": suggestions.prompts,
            "node_trace": [NodeName.GENERATE_SUGGESTIONS],
            **_llm_usage_update(
                self._assistant_service,
                NodeName.GENERATE_SUGGESTIONS,
                "suggestion_generation",
            ),
        }

    @log_node(NodeName.CLARIFICATION_RESPONSE)
    async def clarification_response(self, state: PortfolioState) -> dict:
        return {
            "final_answer": state.get("clarification_question", "Can you clarify which project or role you mean?"),
            "node_trace": [NodeName.CLARIFICATION_RESPONSE],
        }

    @log_node(NodeName.FRIENDLY_RESPONSE)
    async def friendly_response(self, state: PortfolioState) -> dict:
        answer = self._assistant_service.build_friendly_response(
            assistant_subject=state.get("assistant_subject", "the portfolio owner"),
            intent=state.get("intent"),
        )
        return {
            "final_answer": answer,
            "node_trace": [NodeName.FRIENDLY_RESPONSE],
        }

    @log_node(NodeName.SAVE_MEMORY)
    async def save_memory(self, state: PortfolioState) -> dict:
        existing_history = list(state.get("messages", []))
        final_answer = state.get("final_answer", "").strip()
        user_query = state.get("user_query", "").strip()
        if final_answer and user_query:
            existing_history.append({"user": user_query, "assistant": final_answer})
        if len(existing_history) > self._settings.session_history_max_turns:
            existing_history = existing_history[-self._settings.session_history_max_turns :]

        return {
            "messages": existing_history,
            "llm_usage_total": _sum_llm_usage(state.get("llm_usage", [])),
            "node_trace": [NodeName.SAVE_MEMORY],
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


def _llm_usage_update(assistant_service: AssistantService, node_name: NodeName, operation: str) -> dict:
    consume = getattr(assistant_service, "consume_token_usage", None)
    if not callable(consume):
        return {}
    usage = consume(operation)
    if not usage:
        return {}
    return {
        "llm_usage": [
            {
                "node": node_name.value,
                "operation": operation,
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "total_tokens": usage["total_tokens"],
            }
        ]
    }


def _sum_llm_usage(events: list[dict]) -> dict[str, int]:
    return {
        "input_tokens": sum(int(event.get("input_tokens", 0)) for event in events),
        "output_tokens": sum(int(event.get("output_tokens", 0)) for event in events),
        "total_tokens": sum(int(event.get("total_tokens", 0)) for event in events),
    }


SUGGESTION_INTENTS = {
    "projects",
    "project",
    "skills",
    "experience",
    "resume",
    "profile",
    "professional_fit",
    "work_experience",
}

NO_SUGGESTION_INTENTS = {
    "education",
    "contact",
    "policy_violation",
    "user_task",
    "off_topic",
}


def _should_generate_suggestions(state: PortfolioState) -> bool:
    if state.get("route") != "portfolio_query":
        return False
    if state.get("needs_clarification"):
        return False
    if not state.get("final_answer", "").strip():
        return False

    intent = (state.get("intent") or "").lower()
    if intent in NO_SUGGESTION_INTENTS:
        return False
    if intent in SUGGESTION_INTENTS:
        return True

    sources = set(state.get("retrieval_sources", []))
    return "projects" in sources or len(sources) > 1


POLICY_VIOLATION_PATTERNS = (
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|bypass|override|forget)\b.{0,80}\b("
            r"previous|prior|above|system|developer|instructions?|rules?|prompt"
            r")\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "prompt_extraction",
        re.compile(
            r"\b("
            r"system prompt|hidden (?:prompt|instructions?|developer messages?)|"
            r"developer messages?|exact instructions?|print .*instructions?"
            r")\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "portfolio_fabrication",
        re.compile(
            r"\b("
            r"pretend|invent|fabricate|make up|fake"
            r")\b.{0,100}\b("
            r"portfolio|project|experience|resume|recruiters?|built|worked"
            r")\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "secret_or_credential_request",
        re.compile(
            r"\b("
            r"aws root keys?|api keys?|access tokens?|secret keys?|credentials?|passwords?|private keys?"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "harmful_content",
        re.compile(
            r"\b("
            r"malware|ransomware|keylogger|phishing|credential theft|steal credentials|banking trojan"
            r")\b",
            re.IGNORECASE,
        ),
    ),
)


def _detect_policy_violation(query: str) -> str | None:
    for reason, pattern in POLICY_VIOLATION_PATTERNS:
        if pattern.search(query):
            return reason
    return None


AMBIGUOUS_REFERENCE_PATTERNS = (
    re.compile(r"\b(first|second|third)\s+(one|project|role)\b", re.IGNORECASE),
    re.compile(r"\b(this|that)\s+(project|role|one)\b", re.IGNORECASE),
    re.compile(r"\b(previous|earlier)\s+(project|role|one)\b", re.IGNORECASE),
    re.compile(r"\b(mentioned above|above)\b", re.IGNORECASE),
)
LIST_ITEM_PATTERNS = (
    re.compile(r"^\s*(?:\d+\.|-)\s+\*\*(.+?)\*\*", re.MULTILINE),
    re.compile(r'^\s*(?:\d+\.|-)\s+"([^"]+)"', re.MULTILINE),
    re.compile(r"^\s*(?:\d+\.|-)\s+([A-Za-z0-9][A-Za-z0-9 ._-]{1,60}?)(?:\s*[:-]|\s*$)", re.MULTILINE),
)
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "have",
    "about",
    "more",
    "details",
    "project",
    "mentioned",
    "provide",
    "what",
    "which",
    "tool",
    "using",
    "used",
}


def _is_ambiguous_reference(query: str) -> bool:
    return any(pattern.search(query) for pattern in AMBIGUOUS_REFERENCE_PATTERNS)


def _extract_recent_list_candidates(messages: list[dict]) -> list[dict[str, str]]:
    for turn in reversed(messages):
        assistant_text = turn.get("assistant", "")
        candidates = _extract_list_candidates(assistant_text)
        if len(candidates) >= 2:
            return candidates
    return []


def _extract_list_candidates(text: str) -> list[dict[str, str]]:
    candidates = _extract_numbered_candidate_entries(text)
    if candidates:
        return candidates

    seen: set[str] = set()
    fallback_candidates: list[dict[str, str]] = []
    for pattern in LIST_ITEM_PATTERNS:
        for match in pattern.findall(text):
            candidate = match.strip().strip(" .,:;!?")
            if len(candidate) < 2:
                continue
            lowered = candidate.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            fallback_candidates.append({"name": candidate, "details": ""})
    return fallback_candidates


def _extract_numbered_candidate_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    lines = text.splitlines()
    current_name: str | None = None
    current_details: list[str] = []

    def flush() -> None:
        nonlocal current_name, current_details
        if current_name:
            entries.append(
                {
                    "name": current_name,
                    "details": " ".join(detail.strip() for detail in current_details if detail.strip()),
                }
            )
        current_name = None
        current_details = []

    for line in lines:
        stripped = line.strip()
        numbered_match = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", stripped)
        if numbered_match:
            flush()
            current_name = numbered_match.group(1).strip()
            continue
        if current_name and stripped.startswith("-"):
            current_details.append(stripped.lstrip("-").strip())
            continue
        if current_name and not stripped:
            continue
        if current_name:
            flush()

    flush()
    return entries


def _resolve_unique_candidate_from_query(query: str, candidates: list[dict[str, str]]) -> str | None:
    normalized_query = query.lower()

    name_matches = [candidate["name"] for candidate in candidates if candidate["name"].lower() in normalized_query]
    if len(name_matches) == 1:
        return name_matches[0]

    query_tokens = _meaningful_tokens(query)
    if not query_tokens:
        return None

    scored_candidates: list[tuple[str, int]] = []
    for candidate in candidates:
        candidate_tokens = _meaningful_tokens(f"{candidate['name']} {candidate['details']}")
        overlap = len(query_tokens & candidate_tokens)
        if overlap:
            scored_candidates.append((candidate["name"], overlap))

    if not scored_candidates:
        return None

    scored_candidates.sort(key=lambda item: item[1], reverse=True)
    best_name, best_score = scored_candidates[0]
    if best_score < 2:
        return None
    if len(scored_candidates) > 1 and scored_candidates[1][1] == best_score:
        return None
    return best_name


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _build_clarification_question(query: str, candidates: list[str]) -> str:
    subject = "role" if "role" in query.lower() else "project"
    options = candidates[:3]
    if len(options) == 2:
        options_text = f"{options[0]} or {options[1]}"
    else:
        options_text = ", ".join(options[:-1]) + f", or {options[-1]}"
    return f"Which {subject} do you mean: {options_text}?"
