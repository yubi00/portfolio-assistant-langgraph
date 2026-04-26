# LangGraph Portfolio Assistant

LangGraph-powered implementation of a generic portfolio assistant.

This implementation's architecture and decision log live in `LANGGRAPH_ARCHITECTURE.md`.

## Current Scope

- FastAPI application
- `uv` project setup
- LangGraph `StateGraph`
- Nodes for ingest, context resolution, relevance classification, retrieval planning, retrieval, context merge, answer generation, and friendly off-topic responses
- Conditional routing for portfolio and off-topic prompts
- Real OpenAI calls through `langchain-openai`
- File-backed system prompts under `app/prompts/`

## Phase 1 Routing Policy

The graph uses explicit route categories rather than a loose yes/no classifier:

- `portfolio_query`: questions about the subject's projects, resume, work history, skills, contact details, self-introduction, or professional fit
- `off_topic`: general knowledge, coding/debugging help, or requests to work on the user's own project

This mirrors the production assistant boundary: it may discuss whether the portfolio subject has relevant experience, but it should not become a general coding assistant.

## Phase 2 Retrieval Planning

Portfolio queries now pass through a planning node before answer generation. The node selects the smallest useful source set from:

- `projects`
- `resume`
- `docs`

Phase 3 adds first-pass retrieval:

- `projects` from GitHub using `GITHUB_OWNER` and optional `GITHUB_TOKEN`; forks are excluded by default
- `resume` and `docs` from local text/markdown files
- merged context passed into answer generation
- planned retrieval sources fan out to selected retrievers and then merge before answer generation

PDF/DOCX resume ingestion and vector/RAG retrieval are deferred until later.

## Setup

```powershell
uv sync --dev
Copy-Item .env.example .env
```

Fill in `OPENAI_API_KEY`, `ASSISTANT_SUBJECT`, and optionally `GITHUB_OWNER` / `GITHUB_TOKEN` in `.env`.

For resume-backed answers, add your resume as either:

- `data/resume.md`
- `data/resume.pdf`

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

API session memory is now available through `session_id`. Omit it on the first request, then reuse the returned `session_id` on follow-up requests.

The current memory model is a bounded app-level session store. LangGraph checkpointers were evaluated and intentionally deferred because this repo currently only needs short-term conversational memory, not durable thread persistence.

Streaming is available through `POST /prompt/stream` using Server-Sent Events (SSE).

```powershell
Invoke-WebRequest -Method Post http://127.0.0.1:8000/prompt/stream `
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

Use `--context` only for temporary ad-hoc facts during manual testing. For normal usage, place your resume at `data/resume.md` or `data/resume.pdf` and let the app load it automatically.

Use `--resume-path` only when you want to override the default resume source for a single CLI run:

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

For API runs, the logs now correlate transport and graph execution with:

- `request_id`: unique per HTTP request
- `session_id`: stable across follow-up requests in the same conversation

That means one `/prompt` or `/prompt/stream` call can be followed from the API log line into the graph node logs without external tracing infrastructure.

## Current Limitation

Resume PDF loading is supported from `data/resume.pdf`, but richer PDF/DOCX ingestion and RAG are intentionally deferred.

The streaming implementation emits these SSE events:

- `session_started`
- `progress`
- `answer_chunk`
- `answer_completed`
- `error`

It reuses the existing prompt runner and session handling. The current version streams real `generate_answer` model output from the graph as it arrives, emits stable `progress` milestones for important graph steps, lightly buffers tiny token fragments into more natural text chunks, and then sends final response metadata when the run completes.
