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
        "portfolio_context": request.portfolio_context if request.portfolio_context is not None else settings.portfolio_context,
    }

    result = await graph.ainvoke(initial_state)
    return PromptResponse(
        answer=result.get("final_answer", ""),
        is_relevant=bool(result.get("is_relevant", False)),
        intent=result.get("intent"),
        route=result.get("route"),
        rewritten_query=result.get("rewritten_query", request.prompt),
        node_trace=result.get("node_trace", []),
    )
