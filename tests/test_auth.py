from fastapi.testclient import TestClient

from app import main as app_main
from app.api import prompt as prompt_api
from app.config import Settings, get_settings
from app.main import create_app
from app.schemas import PromptResponse
from app.services.auth_tokens import mint_access_token, mint_refresh_token


def _build_test_settings(**overrides) -> Settings:
    values = {
        "OPENAI_API_KEY": "test",
        "ASSISTANT_SUBJECT": "Alex",
        "AUTH_SIGNING_SECRET": "test-secret-with-at-least-32-bytes",
        "TURNSTILE_BYPASS": True,
        "AUTH_COOKIE_SECURE": False,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def _client(monkeypatch, settings):
    monkeypatch.setattr(app_main, "require_settings", lambda: settings)
    client = TestClient(create_app())
    client.app.dependency_overrides[get_settings] = lambda: settings
    return client


def _assert_error(response, *, status: int, code: str) -> None:
    assert response.status_code == status
    body = response.json()
    assert body["error"]["status"] == status
    assert body["error"]["code"] == code


def test_auth_session_sets_refresh_cookie_and_token_endpoint_mints_access_token(monkeypatch):
    settings = _build_test_settings()
    client = _client(monkeypatch, settings)

    session_response = client.post("/auth/session", json={"turnstile_token": "dummy"})

    assert session_response.status_code == 200
    assert session_response.json() == {"authenticated": True, "refresh_expires_in": 1800}
    assert settings.auth_refresh_cookie_name in session_response.cookies

    token_response = client.post("/auth/token")

    assert token_response.status_code == 200
    body = token_response.json()
    assert body["access_token"]
    assert body["expires_in"] == 60


def test_auth_token_requires_refresh_cookie(monkeypatch):
    settings = _build_test_settings()
    client = _client(monkeypatch, settings)

    response = client.post("/auth/token")

    _assert_error(response, status=401, code="AUTH_REQUIRED")


def test_auth_session_rejects_short_signing_secret(monkeypatch):
    settings = _build_test_settings(AUTH_SIGNING_SECRET="too-short")
    client = _client(monkeypatch, settings)

    response = client.post("/auth/session", json={"turnstile_token": "dummy"})

    _assert_error(response, status=503, code="AUTH_CONFIGURATION_ERROR")


def test_auth_session_rejects_disallowed_origin(monkeypatch):
    settings = _build_test_settings(AUTH_ALLOWED_ORIGINS="https://portfolio.example")
    client = _client(monkeypatch, settings)

    response = client.post(
        "/auth/session",
        json={"turnstile_token": "dummy"},
        headers={"Origin": "https://evil.example"},
    )

    _assert_error(response, status=403, code="ORIGIN_NOT_ALLOWED")


def test_auth_session_rate_limit_returns_429(monkeypatch):
    settings = _build_test_settings(AUTH_SESSION_RATE_LIMIT="1/minute")
    client = _client(monkeypatch, settings)

    first_response = client.post("/auth/session", json={"turnstile_token": "dummy"})
    second_response = client.post("/auth/session", json={"turnstile_token": "dummy"})

    assert first_response.status_code == 200
    _assert_error(second_response, status=429, code="RATE_LIMIT_EXCEEDED")


def test_prompt_requires_access_token_when_auth_enabled(monkeypatch):
    settings = _build_test_settings(REQUIRE_AUTH=True)
    client = _client(monkeypatch, settings)

    response = client.post("/prompt", json={"prompt": "What projects has Alex built?"})

    _assert_error(response, status=401, code="AUTH_REQUIRED")


def test_prompt_accepts_valid_access_token_when_auth_enabled(monkeypatch):
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

    settings = _build_test_settings(REQUIRE_AUTH=True)
    access_token, _ = mint_access_token(settings, session_id="test-session")
    monkeypatch.setattr(prompt_api, "run_prompt", fake_run_prompt)
    client = _client(monkeypatch, settings)

    response = client.post(
        "/prompt",
        json={"prompt": "What projects has Alex built?"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "answer"


def test_prompt_rejects_wrong_token_type(monkeypatch):
    settings = _build_test_settings(REQUIRE_AUTH=True)
    refresh_token, _ = mint_refresh_token(settings)
    client = _client(monkeypatch, settings)

    response = client.post(
        "/prompt",
        json={"prompt": "What projects has Alex built?"},
        headers={"Authorization": f"Bearer {refresh_token}"},
    )

    _assert_error(response, status=401, code="INVALID_TOKEN")
