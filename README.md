# LangGraph Portfolio Assistant

LangGraph-powered implementation of a generic portfolio assistant.

This implementation's architecture and decision log live in `LANGGRAPH_ARCHITECTURE.md`.

## Current Scope

- FastAPI application
- `uv` project setup
- LangGraph `StateGraph`
- Nodes for ingest, context resolution, relevance classification, retrieval planning, retrieval, context merge, answer generation, and friendly off-topic responses
- Conditional routing for portfolio, identity, and off-topic prompts
- Real OpenAI calls through `langchain-openai`
- File-backed system prompts under `app/prompts/`

## Phase 1 Routing Policy

The graph uses explicit route categories rather than a loose yes/no classifier:

- `portfolio_query`: questions about the subject's projects, resume, work history, skills, contact details, or professional fit
- `assistant_identity`: questions like "who are you?" or "what can you do?"
- `off_topic`: general knowledge, coding/debugging help, or requests to work on the user's own project

This mirrors the production assistant boundary: it may discuss whether the portfolio subject has relevant experience, but it should not become a general coding assistant.

## Phase 2 Retrieval Planning

Portfolio queries now pass through a planning node before answer generation. The node selects the smallest useful source set from:

- `profile`
- `projects`
- `resume`
- `work_history`
- `docs`

Phase 3 adds first-pass retrieval:

- `projects` from GitHub using `GITHUB_OWNER` and optional `GITHUB_TOKEN`; forks are excluded by default
- `resume`, `work_history`, and `docs` from local text/markdown files
- merged context passed into answer generation
- planned retrieval sources fan out to selected retrievers and then merge before answer generation

PDF/DOCX resume ingestion and vector/RAG retrieval are deferred until later.

## Setup

```powershell
uv sync --dev
Copy-Item .env.example .env
```

Fill in `OPENAI_API_KEY` in `.env`. Optional: set `ASSISTANT_SUBJECT`, `GITHUB_OWNER`, and `GITHUB_TOKEN`.

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

With `--show-trace`, portfolio queries also print planned sources and the planner reason.

Interactive prompt loop:

```powershell
uv run portfolio-assistant
```

Use `--subject` to override the configured portfolio subject for a single run:

```powershell
uv run portfolio-assistant "What projects has Yubi built?" --subject "Yubi"
```

Use `--context` only for temporary ad-hoc facts during manual testing. Prefer `--resume-path` for profile, skills, and work-history data.

Use `--resume-path` when testing resume/work-history questions without editing `.env`:

```powershell
uv run portfolio-assistant "what is Yubi's work experience?" `
  --subject "Yubi" `
  --resume-path "data/processed/resume.md" `
  --show-trace
```

For PDF resumes, convert to Markdown first:

```powershell
uv run python scripts/convert_resume_pdf.py resume.pdf data/processed/resume.md
```

Resume files and processed outputs are ignored by git because they usually contain private data.

## Logging

The app logs graph node execution and route decisions with Python's standard `logging` module.

```powershell
uv run portfolio-assistant "who are you" --show-trace --log-level INFO
```

Use `--log-level DEBUG` for more verbose local runs, or `--log-level WARNING` when you only want warnings/errors. Use `--no-log-color` to disable ANSI colors.

## Current Limitation

Resume PDF/DOCX ingestion is still manual: convert PDF to Markdown first, then pass the processed file with `--resume-path`. Vector/RAG retrieval is intentionally deferred.
