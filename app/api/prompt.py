import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.schemas import ConversationTurn, PromptRequest, PromptResponse
from app.services.prompt_runner import run_prompt, run_prompt_stream
from app.services.session_store import InMemorySessionStore, SessionNotFoundError

router = APIRouter()
STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/prompt", response_model=PromptResponse)
async def prompt(
    request: PromptRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
) -> PromptResponse:
    try:
        session_store, session_id, effective_request = _prepare_effective_request(request, http_request)
        response = await run_prompt(effective_request, settings)
        session_store.set_history(session_id, [turn.model_dump() for turn in response.history])
        return response
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Prompt processing failed.") from exc


@router.post("/prompt/stream")
async def prompt_stream(
    request: PromptRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    try:
        session_store, session_id, effective_request = _prepare_effective_request(request, http_request)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(
        _stream_prompt_response(effective_request, settings, session_store, session_id),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


def _prepare_effective_request(
    request: PromptRequest,
    http_request: Request,
) -> tuple[InMemorySessionStore, str, PromptRequest]:
    session_store: InMemorySessionStore = http_request.app.state.session_store
    session_id = request.session_id or session_store.create_session()
    stored_history = session_store.get_history(session_id)
    merged_history = [*stored_history, *request.history]
    effective_request = request.model_copy(
        update={
            "session_id": session_id,
            "history": [ConversationTurn(**turn) for turn in merged_history],
        }
    )
    return session_store, session_id, effective_request


async def _stream_prompt_response(
    request: PromptRequest,
    settings: Settings,
    session_store: InMemorySessionStore,
    session_id: str,
) -> AsyncIterator[str]:
    chunk_buffer = _AnswerChunkBuffer(settings.stream_chunk_buffer_chars)
    yield _format_sse_event("session_started", {"session_id": session_id})
    try:
        async for event in run_prompt_stream(request, settings):
            if event["type"] == "progress":
                buffered_chunk = chunk_buffer.flush()
                if buffered_chunk:
                    yield _format_sse_event("answer_chunk", {"session_id": session_id, "delta": buffered_chunk})
                yield _format_sse_event("progress", {"session_id": session_id, **event["data"]})
                continue
            if event["type"] == "answer_completed":
                buffered_chunk = chunk_buffer.flush()
                if buffered_chunk:
                    yield _format_sse_event("answer_chunk", {"session_id": session_id, "delta": buffered_chunk})
                response = PromptResponse(**event["data"])
                session_store.set_history(session_id, [turn.model_dump() for turn in response.history])
                yield _format_sse_event("answer_completed", response.model_dump())
                continue
            if event["type"] == "answer_chunk":
                buffered_chunk = chunk_buffer.push(event["data"])
                if buffered_chunk:
                    yield _format_sse_event("answer_chunk", {"session_id": session_id, "delta": buffered_chunk})
    except Exception:
        buffered_chunk = chunk_buffer.flush()
        if buffered_chunk:
            yield _format_sse_event("answer_chunk", {"session_id": session_id, "delta": buffered_chunk})
        yield _format_sse_event(
            "error",
            {
                "session_id": session_id,
                "detail": "Prompt processing failed.",
            },
        )


def _format_sse_event(event_name: str, data: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


class _AnswerChunkBuffer:
    def __init__(self, max_chars: int) -> None:
        self._max_chars = max_chars
        self._buffer = ""

    def push(self, chunk: str) -> str | None:
        self._buffer += chunk
        if self._should_flush():
            return self.flush()
        return None

    def flush(self) -> str | None:
        if not self._buffer:
            return None
        flushed = self._buffer
        self._buffer = ""
        return flushed

    def _should_flush(self) -> bool:
        if len(self._buffer) >= self._max_chars:
            return True
        return self._buffer.endswith((" ", "\n", ".", ",", "!", "?", ":", ";"))
