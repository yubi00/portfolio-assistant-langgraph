# LangGraph Portfolio Assistant

Learning-focused LangGraph implementation of a generic portfolio assistant.

The production assistant architecture is documented in `ARCHITECTURE_OLD_SYSTEM.md`; this repo rebuilds the behavior phase by phase with explicit LangGraph orchestration.

This implementation's architecture and decision log live in `LANGGRAPH_ARCHITECTURE.md`.

## Phase 0/1 Scope

- FastAPI application
- `uv` project setup
- Minimal LangGraph `StateGraph`
- Nodes for ingest, context resolution, relevance classification, answer generation, and friendly off-topic responses
- Conditional routing for relevant vs. irrelevant prompts
- Real OpenAI calls through `langchain-openai`
- File-backed system prompts under `app/prompts/`

## Phase 1 Routing Policy

The graph uses explicit route categories rather than a loose yes/no classifier:

- `portfolio_query`: questions about the subject's projects, resume, work history, skills, contact details, or professional fit
- `assistant_identity`: questions like "who are you?" or "what can you do?"
- `off_topic`: general knowledge, coding/debugging help, or requests to work on the user's own project

This mirrors the production assistant boundary: it may discuss whether the portfolio subject has relevant experience, but it should not become a general coding assistant.

## Setup

```powershell
uv sync --dev
Copy-Item .env.example .env
```

Fill in `OPENAI_API_KEY` in `.env`. Optional: set `ASSISTANT_SUBJECT` and `PORTFOLIO_CONTEXT` for a specific portfolio owner.

## Run

```powershell
uv run uvicorn app.main:app --reload
```

Then call:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/prompt `
  -ContentType "application/json" `
  -Body '{"prompt":"What projects has this person built?"}'
```

## CLI

One-shot prompt:

```powershell
uv run portfolio-assistant "What projects has this person built?" --show-trace
```

Interactive prompt loop:

```powershell
uv run portfolio-assistant
```

Use `--subject` and `--context` to override `.env` values for a single run:

```powershell
uv run portfolio-assistant "What skills are strongest?" `
  --subject "Alex" `
  --context "Alex is a backend engineer with Python, FastAPI, and LangGraph experience."
```

## Current Limitation

Phase 1 does not retrieve GitHub, resume, or docs data yet. If `PORTFOLIO_CONTEXT` is empty, the assistant must say that it does not have enough portfolio data instead of inventing details.
