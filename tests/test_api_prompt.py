from fastapi.testclient import TestClient

from app import main as app_main
from app.api import prompt as prompt_api
from app.config import Settings, SettingsError, get_settings
from app.main import create_app
from app.schemas import PromptResponse


def _test_settings() -> Settings:
    return Settings(_env_file=None, OPENAI_API_KEY="test", ASSISTANT_SUBJECT="Alex")


def test_prompt_route_creates_session_and_reuses_history(monkeypatch):
    calls: list[dict] = []

    async def fake_run_prompt(request, settings):
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
    async def fake_run_prompt(request, settings):
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

    assert response.status_code == 404
    assert "was not found or has expired" in response.json()["detail"]


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

    assert response.status_code == 503
    assert response.json() == {"detail": "Missing config"}
