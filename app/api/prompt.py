from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.schemas import ConversationTurn, PromptRequest, PromptResponse
from app.services.prompt_runner import run_prompt
from app.services.session_store import InMemorySessionStore, SessionNotFoundError

router = APIRouter()


@router.post("/prompt", response_model=PromptResponse)
async def prompt(
    request: PromptRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
) -> PromptResponse:
    session_store: InMemorySessionStore = http_request.app.state.session_store
    try:
        session_id = request.session_id or session_store.create_session()
        stored_history = session_store.get_history(session_id)
        merged_history = [*stored_history, *request.history]
        effective_request = request.model_copy(
            update={
                "session_id": session_id,
                "history": [ConversationTurn(**turn) for turn in merged_history],
            }
        )
        response = await run_prompt(effective_request, settings)
        session_store.set_history(session_id, [turn.model_dump() for turn in response.history])
        return response
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Prompt processing failed.") from exc
