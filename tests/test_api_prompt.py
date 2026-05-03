import asyncio

from fastapi.testclient import TestClient

from app import main as app_main
from app.api import prompt as prompt_api
from app.config import Settings, SettingsError, get_settings
from app.errors import UpstreamServiceError
from app.main import create_app
from app.schemas import PromptResponse


def _build_test_settings(**overrides) -> Settings:
    return Settings(_env_file=None, OPENAI_API_KEY="test", ASSISTANT_SUBJECT="Alex", **overrides)


def _test_settings() -> Settings:
    return _build_test_settings()


def _assert_error(response, *, status: int, code: str, message: str | None = None) -> None:
    assert response.status_code == status
    body = response.json()
    assert body["error"]["status"] == status
    assert body["error"]["code"] == code
    if message is not None:
        assert body["error"]["message"] == message


def test_prompt_route_creates_session_and_reuses_history(monkeypatch):
    calls: list[dict] = []

    async def fake_run_prompt(request, settings, *, request_id=None):
        calls.append(request.model_dump())
        return PromptResponse(
            answer=f"answer: {request.prompt}",
            session_id=request.session_id,
            history=[
                *request.history,
                {"user": request.prompt, "assistant": f"answer: {request.prompt}"},
            ],
            is_relevant=True,
            intent="projects",
            route="portfolio_query",
            retrieval_sources=["projects"],
            retrieval_reason="Project questions need project data.",
            retrieval_errors=[],
            rewritten_query=request.prompt,
            node_trace=["ingest_user_message", "generate_answer"],
        )

    monkeypatch.setattr(prompt_api, "run_prompt", fake_run_prompt)
    monkeypatch.setattr(app_main, "require_settings", _test_settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = _test_settings

    first_response = client.post("/prompt", json={"prompt": "What projects has Alex built?"})
    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["session_id"]

    second_response = client.post(
        "/prompt",
        json={
            "prompt": "Tell me more about the first one",
            "session_id": first_body["session_id"],
        },
    )
    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["session_id"] == first_body["session_id"]

    assert calls[0]["history"] == []
    assert calls[1]["history"] == [
        {
            "user": "What projects has Alex built?",
            "assistant": "answer: What projects has Alex built?",
        }
    ]


def test_prompt_route_returns_404_for_unknown_session(monkeypatch):
    async def fake_run_prompt(request, settings, *, request_id=None):
        return PromptResponse(
            answer="answer",
            session_id=request.session_id,
            history=[],
            is_relevant=True,
            intent="projects",
            route="portfolio_query",
            retrieval_sources=["projects"],
            retrieval_reason="Project questions need project data.",
            retrieval_errors=[],
            rewritten_query=request.prompt,
            node_trace=["ingest_user_message", "generate_answer"],
        )

    monkeypatch.setattr(prompt_api, "run_prompt", fake_run_prompt)
    monkeypatch.setattr(app_main, "require_settings", _test_settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = _test_settings

    response = client.post("/prompt", json={"prompt": "Hello", "session_id": "missing-session"})

    _assert_error(response, status=404, code="SESSION_NOT_FOUND")
    assert "was not found or has expired" in response.json()["error"]["message"]


def test_app_startup_initializes_graph(monkeypatch):
    calls: list[str] = []

    def fake_get_portfolio_graph():
        calls.append("initialized")
        return object()

    monkeypatch.setattr(app_main, "get_portfolio_graph", fake_get_portfolio_graph)
    monkeypatch.setattr(app_main, "require_settings", _test_settings)

    with TestClient(create_app()) as client:
        assert client.get("/").status_code == 200

    assert calls == ["initialized"]


def test_create_app_returns_configuration_error_app_when_settings_are_invalid(monkeypatch):
    monkeypatch.setattr(app_main, "require_settings", lambda: (_ for _ in ()).throw(SettingsError("Missing config")))

    client = TestClient(create_app())
    response = client.get("/")

    _assert_error(response, status=503, code="CONFIGURATION_ERROR", message="Missing config")


def test_create_app_returns_configuration_error_app_for_invalid_rate_limit(monkeypatch):
    monkeypatch.setattr(app_main, "require_settings", lambda: _build_test_settings(PROMPT_RATE_LIMIT="not-a-limit"))

    client = TestClient(create_app())
    response = client.get("/")

    _assert_error(response, status=503, code="CONFIGURATION_ERROR")
    assert "Invalid rate limit setting" in response.json()["error"]["message"]


def test_unknown_route_returns_structured_http_error(monkeypatch):
    monkeypatch.setattr(app_main, "require_settings", _test_settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = _test_settings

    response = client.get("/missing-route")

    _assert_error(response, status=404, code="NOT_FOUND", message="Not Found")


def test_api_docs_are_enabled_outside_production(monkeypatch):
    monkeypatch.setattr(app_main, "require_settings", lambda: _build_test_settings(APP_ENV="development"))

    client = TestClient(create_app())

    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_api_docs_are_hidden_in_production(monkeypatch):
    monkeypatch.setattr(app_main, "require_settings", lambda: _build_test_settings(APP_ENV="production"))

    client = TestClient(create_app())

    _assert_error(client.get("/docs"), status=404, code="NOT_FOUND", message="Not Found")
    _assert_error(client.get("/redoc"), status=404, code="NOT_FOUND", message="Not Found")
    _assert_error(client.get("/openapi.json"), status=404, code="NOT_FOUND", message="Not Found")


def test_prompt_stream_route_emits_sse_events(monkeypatch):
    async def fake_run_prompt_stream(request, settings, *, request_id=None):
        yield {"type": "progress", "data": {"node": "resolve_context", "step": "context_resolved"}}
        yield {"type": "progress", "data": {"node": "plan_retrieval", "step": "retrieval_planned"}}
        yield {"type": "answer_chunk", "data": "First"}
        yield {"type": "answer_chunk", "data": " streamed"}
        yield {"type": "answer_chunk", "data": " sentence. "}
        yield {"type": "answer_chunk", "data": "Second"}
        yield {"type": "answer_chunk", "data": " streamed"}
        yield {"type": "answer_chunk", "data": " sentence."}
        yield {
            "type": "answer_completed",
            "data": PromptResponse(
                answer="First streamed sentence. Second streamed sentence.",
                session_id=request.session_id,
                history=[
                    {"user": request.prompt, "assistant": "First streamed sentence. Second streamed sentence."},
                ],
                is_relevant=True,
                intent="projects",
                route="portfolio_query",
                retrieval_sources=["projects"],
                retrieval_reason="Project questions need project data.",
                retrieval_errors=[],
                rewritten_query=request.prompt,
                node_trace=["ingest_user_message", "generate_answer", "save_memory"],
            ).model_dump(),
        }

    monkeypatch.setattr(prompt_api, "run_prompt_stream", fake_run_prompt_stream)
    monkeypatch.setattr(app_main, "require_settings", _test_settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = _test_settings

    with client.stream("POST", "/prompt/stream", json={"prompt": "What projects has Alex built?"}) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: session_started" in body
    assert "event: progress" in body
    assert "event: answer_chunk" in body
    assert "event: answer_completed" in body
    assert '"step": "context_resolved"' in body
    assert '"retrieval_sources": ["projects"]' in body
    assert body.count("event: answer_chunk") == 2
    assert '"delta": "First streamed sentence. "' in body
    assert '"delta": "Second streamed sentence."' in body


def test_prompt_route_returns_503_for_upstream_ai_failure(monkeypatch):
    async def fake_run_prompt(request, settings, *, request_id=None):
        raise UpstreamServiceError("AI service failed during answer generation.")

    monkeypatch.setattr(prompt_api, "run_prompt", fake_run_prompt)
    monkeypatch.setattr(app_main, "require_settings", _test_settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = _test_settings

    response = client.post("/prompt", json={"prompt": "What projects has Alex built?"})

    _assert_error(
        response,
        status=503,
        code="UPSTREAM_SERVICE_ERROR",
        message="AI service failed during answer generation.",
    )


def test_prompt_route_rate_limit_returns_429(monkeypatch):
    async def fake_run_prompt(request, settings, *, request_id=None):
        return PromptResponse(
            answer="answer",
            session_id=request.session_id,
            history=[{"user": request.prompt, "assistant": "answer"}],
            is_relevant=True,
            intent="projects",
            route="portfolio_query",
            retrieval_sources=["projects"],
            retrieval_reason="Project questions need project data.",
            retrieval_errors=[],
            rewritten_query=request.prompt,
            node_trace=["ingest_user_message", "generate_answer"],
        )

    settings = lambda: _build_test_settings(PROMPT_RATE_LIMIT="1/minute")
    monkeypatch.setattr(prompt_api, "run_prompt", fake_run_prompt)
    monkeypatch.setattr(app_main, "require_settings", settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = settings

    first_response = client.post("/prompt", json={"prompt": "What projects has Alex built?"})
    second_response = client.post("/prompt", json={"prompt": "What projects has Alex built?"})

    assert first_response.status_code == 200
    _assert_error(second_response, status=429, code="RATE_LIMIT_EXCEEDED", message="Rate limit exceeded.")


def test_prompt_stream_emits_upstream_error_event(monkeypatch):
    async def fake_run_prompt_stream(request, settings, *, request_id=None):
        raise UpstreamServiceError("AI service failed during answer streaming.")
        yield

    monkeypatch.setattr(prompt_api, "run_prompt_stream", fake_run_prompt_stream)
    monkeypatch.setattr(app_main, "require_settings", _test_settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = _test_settings

    with client.stream("POST", "/prompt/stream", json={"prompt": "What projects has Alex built?"}) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: error" in body
    assert '"detail": "AI service failed during answer streaming."' in body
    assert '"partial_answer": ""' in body


def test_prompt_stream_preserves_partial_answer_on_upstream_failure(monkeypatch):
    async def fake_run_prompt_stream(request, settings, *, request_id=None):
        yield {"type": "progress", "data": {"node": "generate_answer", "step": "answer_started"}}
        yield {"type": "answer_chunk", "data": "First partial sentence. "}
        raise UpstreamServiceError("AI service failed during answer streaming.")

    monkeypatch.setattr(prompt_api, "run_prompt_stream", fake_run_prompt_stream)
    monkeypatch.setattr(app_main, "require_settings", _test_settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = _test_settings

    with client.stream("POST", "/prompt/stream", json={"prompt": "What projects has Alex built?"}) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: answer_chunk" in body
    assert '"delta": "First partial sentence. "' in body
    assert "event: error" in body
    assert '"detail": "AI service failed during answer streaming."' in body
    assert '"partial_answer": "First partial sentence. "' in body


def test_prompt_stream_rate_limit_returns_429(monkeypatch):
    async def fake_run_prompt_stream(request, settings, *, request_id=None):
        yield {
            "type": "answer_completed",
            "data": PromptResponse(
                answer="answer",
                session_id=request.session_id,
                history=[{"user": request.prompt, "assistant": "answer"}],
                is_relevant=True,
                intent="projects",
                route="portfolio_query",
                retrieval_sources=["projects"],
                retrieval_reason="Project questions need project data.",
                retrieval_errors=[],
                rewritten_query=request.prompt,
                node_trace=["ingest_user_message", "generate_answer"],
            ).model_dump(),
        }

    settings = lambda: _build_test_settings(PROMPT_STREAM_RATE_LIMIT="1/minute")
    monkeypatch.setattr(prompt_api, "run_prompt_stream", fake_run_prompt_stream)
    monkeypatch.setattr(app_main, "require_settings", settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = settings

    first_response = client.post("/prompt/stream", json={"prompt": "What projects has Alex built?"})
    second_response = client.post("/prompt/stream", json={"prompt": "What projects has Alex built?"})

    assert first_response.status_code == 200
    _assert_error(second_response, status=429, code="RATE_LIMIT_EXCEEDED", message="Rate limit exceeded.")


def test_prompt_stream_concurrency_limit_returns_429(monkeypatch):
    async def fake_run_prompt_stream(request, settings, *, request_id=None):
        yield {
            "type": "answer_completed",
            "data": PromptResponse(
                answer="answer",
                session_id=request.session_id,
                history=[{"user": request.prompt, "assistant": "answer"}],
                is_relevant=True,
                intent="projects",
                route="portfolio_query",
                retrieval_sources=["projects"],
                retrieval_reason="Project questions need project data.",
                retrieval_errors=[],
                rewritten_query=request.prompt,
                node_trace=["ingest_user_message", "generate_answer"],
            ).model_dump(),
        }

    settings = lambda: _build_test_settings(MAX_ACTIVE_STREAMS_PER_CLIENT=1)
    monkeypatch.setattr(prompt_api, "run_prompt_stream", fake_run_prompt_stream)
    monkeypatch.setattr(app_main, "require_settings", settings)

    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = settings
    asyncio.run(client.app.state.active_stream_registry.acquire("testclient", 1))

    response = client.post("/prompt/stream", json={"prompt": "What projects has Alex built?"})

    _assert_error(
        response,
        status=429,
        code="STREAM_CONCURRENCY_LIMIT_EXCEEDED",
        message="Too many active streams.",
    )
