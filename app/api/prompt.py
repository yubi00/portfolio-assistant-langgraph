import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.errors import UpstreamServiceError
from app.schemas import ConversationTurn, PromptRequest, PromptResponse
from app.services.prompt_runner import run_prompt, run_prompt_stream
from app.services.session_store import InMemorySessionStore, SessionNotFoundError

router = APIRouter()
logger = logging.getLogger("app.api.prompt")
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
    request_id = _new_request_id()
    started_at = perf_counter()
    try:
        session_store, session_id, effective_request = _prepare_effective_request(request, http_request)
        logger.info(
            "prompt request started | request_id=%s | session_id=%s | prompt=%r",
            request_id,
            session_id,
            _shorten(request.prompt),
        )
        response = await run_prompt(effective_request, settings, request_id=request_id)
        session_store.set_history(session_id, [turn.model_dump() for turn in response.history])
        logger.info(
            "prompt request completed | request_id=%s | session_id=%s | route=%s | intent=%s | duration_ms=%.1f",
            request_id,
            session_id,
            response.route,
            response.intent,
            (perf_counter() - started_at) * 1000,
        )
        return response
    except SessionNotFoundError as exc:
        logger.warning(
            "prompt request failed | request_id=%s | session_id=%s | status=404 | detail=%s",
            request_id,
            request.session_id,
            exc,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning(
            "prompt request failed | request_id=%s | session_id=%s | status=400 | detail=%s",
            request_id,
            request.session_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        logger.warning(
            "prompt request failed | request_id=%s | session_id=%s | status=503 | detail=%s",
            request_id,
            request.session_id,
            exc,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "prompt request failed | request_id=%s | session_id=%s | status=500",
            request_id,
            request.session_id,
        )
        raise HTTPException(status_code=500, detail="Prompt processing failed.") from exc


@router.post("/prompt/stream")
async def prompt_stream(
    request: PromptRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    request_id = _new_request_id()
    started_at = perf_counter()
    try:
        session_store, session_id, effective_request = _prepare_effective_request(request, http_request)
    except SessionNotFoundError as exc:
        logger.warning(
            "prompt stream failed | request_id=%s | session_id=%s | status=404 | detail=%s",
            request_id,
            request.session_id,
            exc,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning(
            "prompt stream failed | request_id=%s | session_id=%s | status=400 | detail=%s",
            request_id,
            request.session_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        logger.warning(
            "prompt stream failed | request_id=%s | session_id=%s | status=503 | detail=%s",
            request_id,
            request.session_id,
            exc,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info(
        "prompt stream started | request_id=%s | session_id=%s | prompt=%r",
        request_id,
        session_id,
        _shorten(request.prompt),
    )

    return StreamingResponse(
        _stream_prompt_response(
            effective_request,
            settings,
            session_store,
            session_id,
            request_id=request_id,
            started_at=started_at,
        ),
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
    request_id: str,
    started_at: float,
) -> AsyncIterator[str]:
    chunk_buffer = _AnswerChunkBuffer(settings.stream_chunk_buffer_chars)
    progress_count = 0
    answer_chunk_count = 0
    partial_answer_parts: list[str] = []
    yield _format_sse_event("session_started", {"session_id": session_id})
    try:
        async for event in run_prompt_stream(request, settings, request_id=request_id):
            if event["type"] == "progress":
                buffered_chunk = chunk_buffer.flush()
                if buffered_chunk:
                    answer_chunk_count += 1
                    partial_answer_parts.append(buffered_chunk)
                    yield _format_sse_event("answer_chunk", {"session_id": session_id, "delta": buffered_chunk})
                progress_count += 1
                yield _format_sse_event("progress", {"session_id": session_id, **event["data"]})
                continue
            if event["type"] == "answer_completed":
                buffered_chunk = chunk_buffer.flush()
                if buffered_chunk:
                    answer_chunk_count += 1
                    partial_answer_parts.append(buffered_chunk)
                    yield _format_sse_event("answer_chunk", {"session_id": session_id, "delta": buffered_chunk})
                response = PromptResponse(**event["data"])
                session_store.set_history(session_id, [turn.model_dump() for turn in response.history])
                logger.info(
                    "prompt stream completed | request_id=%s | session_id=%s | route=%s | intent=%s | progress_events=%s | answer_chunks=%s | duration_ms=%.1f",
                    request_id,
                    session_id,
                    response.route,
                    response.intent,
                    progress_count,
                    answer_chunk_count,
                    (perf_counter() - started_at) * 1000,
                )
                yield _format_sse_event("answer_completed", response.model_dump())
                continue
            if event["type"] == "answer_chunk":
                buffered_chunk = chunk_buffer.push(event["data"])
                if buffered_chunk:
                    answer_chunk_count += 1
                    partial_answer_parts.append(buffered_chunk)
                    yield _format_sse_event("answer_chunk", {"session_id": session_id, "delta": buffered_chunk})
    except UpstreamServiceError as exc:
        buffered_chunk = chunk_buffer.flush()
        if buffered_chunk:
            answer_chunk_count += 1
            partial_answer_parts.append(buffered_chunk)
            yield _format_sse_event("answer_chunk", {"session_id": session_id, "delta": buffered_chunk})
        logger.warning(
            "prompt stream failed | request_id=%s | session_id=%s | progress_events=%s | answer_chunks=%s | duration_ms=%.1f | detail=%s",
            request_id,
            session_id,
            progress_count,
            answer_chunk_count,
            (perf_counter() - started_at) * 1000,
            exc,
        )
        yield _format_sse_event(
            "error",
            {
                "session_id": session_id,
                "detail": str(exc),
                "partial_answer": "".join(partial_answer_parts),
            },
        )
    except Exception:
        buffered_chunk = chunk_buffer.flush()
        if buffered_chunk:
            answer_chunk_count += 1
            partial_answer_parts.append(buffered_chunk)
            yield _format_sse_event("answer_chunk", {"session_id": session_id, "delta": buffered_chunk})
        logger.exception(
            "prompt stream failed | request_id=%s | session_id=%s | progress_events=%s | answer_chunks=%s | duration_ms=%.1f",
            request_id,
            session_id,
            progress_count,
            answer_chunk_count,
            (perf_counter() - started_at) * 1000,
        )
        yield _format_sse_event(
            "error",
            {
                "session_id": session_id,
                "detail": "Prompt processing failed.",
                "partial_answer": "".join(partial_answer_parts),
            },
        )


def _format_sse_event(event_name: str, data: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


def _new_request_id() -> str:
    return uuid4().hex[:12]


def _shorten(value: str, max_chars: int = 80) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + "..."


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
