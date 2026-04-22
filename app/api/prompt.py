from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.schemas import PromptRequest, PromptResponse
from app.services.prompt_runner import run_prompt

router = APIRouter()


@router.post("/prompt", response_model=PromptResponse)
async def prompt(request: PromptRequest, settings: Settings = Depends(get_settings)) -> PromptResponse:
    try:
        return await run_prompt(request, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Prompt processing failed.") from exc
