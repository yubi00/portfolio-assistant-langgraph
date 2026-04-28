from collections.abc import AsyncIterator

from app.config import Settings
from app.graph.constants import NodeName
from app.graph.builder import get_portfolio_graph
from app.schemas import PromptRequest, PromptResponse


async def run_prompt(
    request: PromptRequest,
    settings: Settings,
    *,
    request_id: str | None = None,
) -> PromptResponse:
    """Invoke the portfolio graph from any transport.

    FastAPI and the CLI both call this function so request mapping, defaults,
    and response shaping stay consistent across interfaces.
    """

    graph = get_portfolio_graph()
    result = await graph.ainvoke(build_initial_state(request, settings, request_id=request_id))
    return build_prompt_response(request, result)


async def run_prompt_stream(
    request: PromptRequest,
    settings: Settings,
    *,
    request_id: str | None = None,
) -> AsyncIterator[dict]:
    graph = get_portfolio_graph()
    state_updates: dict = {}
    streamed_answer_parts: list[str] = []
    emitted_progress_steps: set[str] = set()
    answer_started_emitted = False

    async for chunk in graph.astream(
        build_initial_state(request, settings, request_id=request_id),
        stream_mode=["messages", "updates"],
        version="v2",
    ):
        if chunk["type"] == "messages":
            message_chunk, metadata = chunk["data"]
            if metadata.get("langgraph_node") != NodeName.GENERATE_ANSWER.value:
                continue
            if not message_chunk.content:
                continue
            if not answer_started_emitted:
                answer_started_emitted = True
                emitted_progress_steps.add("answer_started")
                yield {
                    "type": "progress",
                    "data": {
                        "node": NodeName.GENERATE_ANSWER.value,
                        "step": "answer_started",
                    },
                }
            streamed_answer_parts.append(message_chunk.content)
            yield {"type": "answer_chunk", "data": message_chunk.content}
            continue

        if chunk["type"] == "updates":
            for progress_event in _progress_events_from_updates(chunk["data"], emitted_progress_steps):
                yield progress_event
            _merge_stream_updates(state_updates, chunk["data"])

    response = build_prompt_response(
        request,
        state_updates,
        answer_override="".join(streamed_answer_parts).strip() or state_updates.get("final_answer", ""),
    )

    if not streamed_answer_parts and response.answer:
        yield {"type": "answer_chunk", "data": response.answer}

    yield {"type": "answer_completed", "data": response.model_dump()}


def build_initial_state(
    request: PromptRequest,
    settings: Settings,
    *,
    request_id: str | None = None,
) -> dict:
    state = {
        "user_query": request.prompt,
        "messages": [turn.model_dump() for turn in request.history],
        "assistant_subject": request.assistant_subject or settings.assistant_subject,
        "portfolio_context": request.portfolio_context or "",
        "session_id": request.session_id,
        "resume_path": request.resume_path,
        "docs_path": request.docs_path or settings.docs_path,
    }
    if request_id:
        state["request_id"] = request_id
    return state


def build_prompt_response(request: PromptRequest, result: dict, answer_override: str | None = None) -> PromptResponse:
    return PromptResponse(
        answer=answer_override if answer_override is not None else result.get("final_answer", ""),
        session_id=request.session_id,
        history=result.get("messages", []),
        is_relevant=bool(result.get("is_relevant", False)),
        intent=result.get("intent"),
        route=result.get("route"),
        retrieval_sources=result.get("retrieval_sources", []),
        retrieval_reason=result.get("retrieval_reason"),
        retrieval_errors=result.get("retrieval_errors", []),
        rewritten_query=result.get("rewritten_query", request.prompt),
        node_trace=result.get("node_trace", []),
    )


def _merge_stream_updates(state_updates: dict, updates: dict) -> None:
    for node_update in updates.values():
        for key, value in node_update.items():
            if key in {"node_trace", "retrieval_errors"}:
                state_updates.setdefault(key, [])
                state_updates[key].extend(value)
            else:
                state_updates[key] = value


PROGRESS_STEP_BY_NODE = {
    NodeName.RESOLVE_CONTEXT.value: "context_resolved",
    NodeName.CLASSIFY_RELEVANCE.value: "relevance_classified",
    NodeName.CHECK_AMBIGUITY.value: "ambiguity_checked",
    NodeName.PLAN_RETRIEVAL.value: "retrieval_planned",
    NodeName.RETRIEVE_PROJECTS.value: "projects_retrieved",
    NodeName.RETRIEVE_RESUME.value: "resume_retrieved",
    NodeName.RETRIEVE_DOCS.value: "docs_retrieved",
    NodeName.MERGE_NORMALIZE_CONTEXT.value: "context_merged",
    NodeName.GENERATE_ANSWER.value: "answer_started",
    NodeName.CLARIFICATION_RESPONSE.value: "answer_started",
    NodeName.FRIENDLY_RESPONSE.value: "answer_started",
    NodeName.SAVE_MEMORY.value: "memory_saved",
}


def _progress_events_from_updates(updates: dict, emitted_steps: set[str]) -> list[dict]:
    events: list[dict] = []
    for node_name in updates:
        step = PROGRESS_STEP_BY_NODE.get(node_name)
        if not step or step in emitted_steps:
            continue
        emitted_steps.add(step)
        events.append(
            {
                "type": "progress",
                "data": {
                    "node": node_name,
                    "step": step,
                },
            }
        )
    return events
