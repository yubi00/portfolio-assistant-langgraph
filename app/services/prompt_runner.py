from app.config import Settings
from app.graph.builder import get_portfolio_graph
from app.schemas import PromptRequest, PromptResponse


async def run_prompt(request: PromptRequest, settings: Settings) -> PromptResponse:
    """Invoke the portfolio graph from any transport.

    FastAPI and the CLI both call this function so request mapping, defaults,
    and response shaping stay consistent across interfaces.
    """

    graph = get_portfolio_graph()
    initial_state = {
        "user_query": request.prompt,
        "messages": [turn.model_dump() for turn in request.history],
        "assistant_subject": request.assistant_subject or settings.assistant_subject,
        "portfolio_context": request.portfolio_context or "",
        "resume_path": request.resume_path,
        "docs_path": request.docs_path or settings.docs_path,
    }

    result = await graph.ainvoke(initial_state)
    return PromptResponse(
        answer=result.get("final_answer", ""),
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
