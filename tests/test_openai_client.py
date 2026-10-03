from types import SimpleNamespace

import pytest

from app.config import Settings
from app.errors import UpstreamServiceError
from app.services.assistant import SuggestedPrompts
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
async def test_resolve_context_skips_standalone_query_even_with_history():
    async def fake_ainvoke(_messages):
        raise AssertionError("standalone queries should not call context resolution")

    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(ainvoke=fake_ainvoke)

    query = "Tell me about MatchCast project"
    resolved = await client.resolve_context(
        query,
        history=[{"user": "What AI projects?", "assistant": "MatchCast is one of them."}],
    )

    assert resolved == query
    assert client.consume_token_usage("context_resolution") is None


@pytest.mark.asyncio
async def test_resolve_context_does_not_treat_last_five_as_follow_up():
    async def fake_ainvoke(_messages):
        raise AssertionError("standalone 'last five' queries should not call context resolution")

    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(ainvoke=fake_ainvoke)

    query = "Can you tell me about your last five projects?"
    resolved = await client.resolve_context(
        query,
        history=[{"user": "Tell me about MatchCast", "assistant": "MatchCast is an AI project."}],
    )

    assert resolved == query


@pytest.mark.asyncio
async def test_resolve_context_rewrites_context_dependent_query_with_history():
    captured_messages = []

    async def fake_ainvoke(messages):
        captured_messages.extend(messages)
        return SimpleNamespace(
            text="Tell me about the MatchCast project",
            usage_metadata={
                "input_tokens": 12,
                "output_tokens": 6,
                "total_tokens": 18,
            },
        )

    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(ainvoke=fake_ainvoke)

    resolved = await client.resolve_context(
        "Tell me more about it",
        history=[{"user": "Tell me about MatchCast", "assistant": "MatchCast is an AI project."}],
    )

    assert resolved == "Tell me about the MatchCast project"
    assert captured_messages
    assert client.consume_token_usage("context_resolution") == {
        "input_tokens": 12,
        "output_tokens": 6,
        "total_tokens": 18,
    }


@pytest.mark.asyncio
async def test_generate_answer_wraps_upstream_failure():
    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(ainvoke=_failing_ainvoke)

    with pytest.raises(UpstreamServiceError, match="answer generation"):
        await client.generate_answer("What projects?", "Alex", "Project data")


@pytest.mark.asyncio
async def test_generate_answer_records_token_usage():
    async def fake_ainvoke(_messages):
        return SimpleNamespace(
            text="answer",
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 4,
                "total_tokens": 14,
            },
        )

    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(ainvoke=fake_ainvoke)

    answer = await client.generate_answer("What projects?", "Alex", "Project data")

    assert answer == "answer"
    assert client.consume_token_usage("answer_generation") == {
        "input_tokens": 10,
        "output_tokens": 4,
        "total_tokens": 14,
    }
    assert client.consume_token_usage("answer_generation") is None


@pytest.mark.asyncio
async def test_classify_and_plan_records_one_structured_call_and_token_usage():
    calls = []
    structured_kwargs = []

    async def fake_ainvoke(_messages, **kwargs):
        calls.append((_messages, kwargs))
        return {
            "raw": SimpleNamespace(
                usage_metadata={
                    "input_tokens": 8,
                    "output_tokens": 2,
                    "total_tokens": 10,
                }
            ),
            "parsed": openai_client_module.RoutingDecision(
                route="portfolio_query",
                intent="projects",
                sources=["projects"],
                reason="Project questions need project data.",
            ),
            "parsing_error": None,
        }

    def fake_structured_output(_model, **kwargs):
        structured_kwargs.append(kwargs)
        return SimpleNamespace(ainvoke=fake_ainvoke)

    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(with_structured_output=fake_structured_output)

    decision = await client.classify_and_plan("What projects?", "Alex")

    assert len(calls) == 1
    assert calls[0][1] == {}
    assert structured_kwargs == [{"include_raw": True, "stream": False}]
    assert decision.intent == "projects"
    assert decision.sources == ["projects"]
    assert decision.reason == "Project questions need project data."
    assert client.consume_token_usage("routing_decision") == {
        "input_tokens": 8,
        "output_tokens": 2,
        "total_tokens": 10,
    }
    assert client.consume_token_usage("retrieval_planning") is None


@pytest.mark.asyncio
async def test_classify_and_plan_rejects_invalid_structured_output():
    async def fake_ainvoke(_messages):
        return {"raw": None, "parsed": None, "parsing_error": "missing sources"}

    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(
        with_structured_output=lambda _model, **_kwargs: SimpleNamespace(ainvoke=fake_ainvoke)
    )

    with pytest.raises(UpstreamServiceError, match="invalid routing decision"):
        await client.classify_and_plan("What projects?", "Alex")


@pytest.mark.asyncio
async def test_generate_suggestions_returns_normalized_structured_prompts():
    captured_messages = []
    structured_kwargs = []

    async def fake_ainvoke(messages):
        captured_messages.extend(messages)
        return SuggestedPrompts(
            prompts=[
                "  How does MatchCast generate audio?  ",
                "How does MatchCast generate audio?",
                "What stack did it use?",
                "",
                "How is it deployed?",
            ]
        )

    def fake_structured_output(_model, **kwargs):
        structured_kwargs.append(kwargs)
        return SimpleNamespace(ainvoke=fake_ainvoke)

    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(with_structured_output=fake_structured_output)

    suggestions = await client.generate_suggestions(
        query="Tell me about MatchCast",
        assistant_subject="Alex",
        portfolio_context="Large MatchCast project context that should not be resent for suggestions",
        answer="MatchCast answer",
        intent="projects",
    )

    assert suggestions.prompts == [
        "How does MatchCast generate audio?",
        "What stack did it use?",
        "How is it deployed?",
    ]
    assert structured_kwargs == [{"include_raw": True, "stream": False}]
    suggestion_input = "\n".join(message[1] for message in captured_messages)
    assert "Assistant answer:\nMatchCast answer" in suggestion_input
    assert "Large MatchCast project context" not in suggestion_input


@pytest.mark.asyncio
async def test_generate_suggestions_wraps_upstream_failure():
    client = OpenAIAssistantClient(_test_settings())
    client._chat = SimpleNamespace(
        with_structured_output=lambda _model, **_kwargs: SimpleNamespace(ainvoke=_failing_ainvoke)
    )

    with pytest.raises(UpstreamServiceError, match="suggestion generation"):
        await client.generate_suggestions(
            query="What projects?",
            assistant_subject="Alex",
            portfolio_context="Project data",
            answer="Answer",
            intent="projects",
        )


async def _failing_ainvoke(_messages):
    raise RuntimeError("boom")
