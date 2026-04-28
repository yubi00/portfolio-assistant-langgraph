from types import SimpleNamespace

import pytest

from app.config import Settings
from app.errors import UpstreamServiceError
from app.services import openai_client as openai_client_module
from app.services.openai_client import OpenAIAssistantClient


def _test_settings() -> Settings:
    return Settings(
        _env_file=None,
        OPENAI_API_KEY="test",
        ASSISTANT_SUBJECT="Alex",
        OPENAI_TIMEOUT_SECONDS=12,
        OPENAI_MAX_RETRIES=4,
    )


def test_openai_client_uses_configured_timeout_and_retries(monkeypatch):
    captured_kwargs = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(openai_client_module, "ChatOpenAI", FakeChatOpenAI)

    OpenAIAssistantClient(_test_settings())

    assert captured_kwargs["timeout"] == 12
    assert captured_kwargs["max_retries"] == 4


@pytest.mark.asyncio
async def test_generate_answer_wraps_upstream_failure():
    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(ainvoke=_failing_ainvoke)

    with pytest.raises(UpstreamServiceError, match="answer generation"):
        await client.generate_answer("What projects?", "Alex", "Project data")


async def _failing_ainvoke(_messages):
    raise RuntimeError("boom")
