# LangGraph Portfolio Assistant

LangGraph-powered implementation of a generic portfolio assistant.

This implementation's architecture and decision log live in `LANGGRAPH_ARCHITECTURE.md`.

## Main Features

- grounded portfolio Q&A across `projects`, `resume`, and `docs`
- history-aware contextual follow-up handling
- deterministic policy guard for prompt injection, prompt extraction, unsafe fabrication, secrets, and harmful-content requests
- clarification guard rail for genuinely ambiguous follow-up references
- explicit retrieval planning before answer generation
- targeted GitHub project deep dives when a query names a specific repository
- multi-source context merge with bounded context size
- API session memory via `session_id`
- CLI and FastAPI transports backed by the same graph runner
- SSE streaming via `POST /prompt/stream`
- request/session-aware logging with optional JSON log format
- basic upstream reliability controls with retries, timeouts, and streaming partial-answer preservation
- public API abuse protection with request rate limits and active stream concurrency limits
- optional browser auth for public deployments: Turnstile bootstrap, HttpOnly refresh cookie, and short-lived bearer access tokens

## What Makes It Special

This assistant is not just a single-prompt chatbot over a resume.

What makes it different:

- it uses an explicit LangGraph orchestration flow instead of burying behavior inside one prompt
- it rewrites follow-up questions into standalone queries before planning retrieval
- it chooses the smallest useful source set before answering instead of always dumping all context into the model
- it focuses project retrieval on one named repository for deeper project-specific questions
- it has a clarification guard rail for genuinely ambiguous follow-ups instead of guessing blindly
- it supports both request/response and SSE streaming while reusing the same core graph runner
- it keeps the architecture simple enough to extend without turning into an overengineered agent system

## Current Scope

- FastAPI application
- `uv` project setup
- LangGraph `StateGraph`
- Nodes for ingest, context resolution, policy guard, relevance classification, ambiguity checking, retrieval planning, retrieval, context merge, answer generation, clarification response, and friendly off-topic responses
- Conditional routing for portfolio and off-topic prompts
- Real OpenAI calls through `langchain-openai`
- File-backed system prompts under `app/prompts/`

## Phase 1 Routing Policy

The graph uses explicit route categories rather than a loose yes/no classifier:

- `portfolio_query`: questions about the subject's projects, resume, work history, skills, contact details, self-introduction, or professional fit
- `off_topic`: general knowledge, coding/debugging help, or requests to work on the user's own project

This mirrors the production assistant boundary: it may discuss whether the portfolio subject has relevant experience, but it should not become a general coding assistant.

Before relevance classification, the graph runs a lightweight deterministic policy guard. It blocks common jailbreak and abuse patterns such as instruction override attempts, hidden prompt extraction, fake portfolio claims, secret/credential requests, and harmful-content requests. This keeps obvious unsafe prompts out of retrieval and answer generation without adding another LLM call.

## Phase 2 Retrieval Planning

Portfolio queries now pass through a planning node before answer generation. The node selects the smallest useful source set from:

- `projects`
- `resume`
- `docs`

Phase 3 adds first-pass retrieval:

- `projects` from GitHub using `GITHUB_OWNER` and optional `GITHUB_TOKEN`; forks are excluded by default
- README excerpts are fetched best-effort for each selected repository when available
- named project questions focus retrieval on the matching repository and use a larger README excerpt budget
- `resume` from Neon pgvector when `NEON_DATABASE_URL_STRING` is configured
- explicit `resume_path` local-file override for development and debugging
- `docs` from local text/markdown files
- merged context passed into answer generation
- planned retrieval sources fan out to selected retrievers and then merge before answer generation

PDF/DOCX resume ingestion into the vector store is deferred. Current production-style resume RAG expects Markdown input.

## Resume Vector Indexing

Resume RAG work starts with explicit offline ingestion. The API server should not generate embeddings during startup.

Set these values before indexing:

```powershell
$env:NEON_DATABASE_URL_STRING="postgresql://..."
$env:OPENAI_API_KEY="..."
```

Then run:

```powershell
uv run portfolio-index-resume --resume-path data/resume.md
```

Equivalent module form:

```powershell
uv run python -m scripts.index_resume --resume-path data/resume.md
```

Useful options:

```powershell
uv run portfolio-index-resume --resume-path data/resume.md --dry-run
uv run portfolio-index-resume --resume-path data/resume.md --force
```

The indexer creates the pgvector schema, normalizes raw resume text into semantic Markdown sections, embeds chunks with `OPENAI_EMBEDDING_MODEL`, and upserts by stable document/chunk hashes. Re-running the command exits before embedding when the stored document and chunk hashes are unchanged.

Resume chunking is section-aware. Plain resume labels such as `PROFILE`, `CORE SKILLS`, `SELECTED AI PROJECTS`, `EXPERIENCE`, `EDUCATION`, and `CERTIFICATIONS` are promoted to Markdown headings before chunking, with project/role/education entries promoted to subsections where appropriate.

When `NEON_DATABASE_URL_STRING` is configured, normal resume-related assistant queries retrieve top-k chunks from pgvector instead of injecting the full local resume. The CLI/API still allow `resume_path` as an explicit local-file override for development.

## Setup

```powershell
uv sync --dev
Copy-Item .env.example .env
```

Fill in `OPENAI_API_KEY`, `ASSISTANT_SUBJECT`, and optionally `GITHUB_OWNER` / `GITHUB_TOKEN` in `.env`. For resume RAG, also set `NEON_DATABASE_URL_STRING` and run the offline indexer after adding or updating `data/resume.md`.

For public browser auth, set `REQUIRE_AUTH=true`, provide a 32+ byte `AUTH_SIGNING_SECRET`, configure `TURNSTILE_SECRET_KEY`, and set `AUTH_ALLOWED_ORIGINS` to the frontend origin list.

Project README enrichment is controlled by `GITHUB_README_MAX_CHARS` for broad project lists and `GITHUB_TARGET_README_MAX_CHARS` for focused named-repository retrieval. Repositories without a README still appear with their normal metadata.

Featured project metadata is loaded from `FEATURED_PROJECTS_PATH`, defaulting to `portfolio/featured_projects.json`. This optional curated layer gives subjective questions such as "most proud of", "favorite", or "flagship project" an explicit preference signal instead of relying only on GitHub recency.

For vector-backed resume answers, add your resume as:

- `data/resume.md`

`data/resume.pdf` can still be used only through the local-file override path. Convert it to Markdown before vector indexing.

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

Ambiguous follow-up questions now have a lightweight clarification guard rail. If context resolution cannot safely identify one target from recent history, the assistant asks a short clarification question instead of guessing.

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

Use `--context` only for temporary ad-hoc facts during manual testing. For normal usage, place your resume at `data/resume.md`, run `portfolio-index-resume`, and let resume-related queries retrieve from pgvector.

Use `--resume-path` only when you want to bypass pgvector and read a local resume source for a single CLI run:

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
Use `--log-format json` or `LOG_FORMAT=json` when you want structured logs for server-side runs or log aggregation.

For API runs, the logs now correlate transport and graph execution with:

- `request_id`: unique per HTTP request
- `session_id`: stable across follow-up requests in the same conversation

That means one `/prompt` or `/prompt/stream` call can be followed from the API log line into the graph node logs without external tracing infrastructure.

JSON logging is opt-in. The default remains colorized text logs for local development.

## Reliability

The app now applies basic reliability controls to OpenAI-backed graph steps:

- configurable request timeout with `OPENAI_TIMEOUT_SECONDS`
- configurable client retries with `OPENAI_MAX_RETRIES`
- non-streaming `/prompt` returns `503` for upstream AI-service failures
- streaming `/prompt/stream` emits an `error` SSE event with the upstream failure detail
- when a stream fails after partial output, the `error` event includes `partial_answer`

## Public API Protection

The API applies lightweight in-process abuse protection:

- `/prompt` rate limit via `PROMPT_RATE_LIMIT`
- `/prompt/stream` rate limit via `PROMPT_STREAM_RATE_LIMIT`
- `/auth/session` rate limit via `AUTH_SESSION_RATE_LIMIT`
- `/auth/token` rate limit via `AUTH_TOKEN_RATE_LIMIT`
- active SSE stream concurrency limit via `MAX_ACTIVE_STREAMS_PER_CLIENT`

Defaults:

```powershell
RATE_LIMIT_ENABLED=true
PROMPT_RATE_LIMIT=30/minute
PROMPT_STREAM_RATE_LIMIT=10/minute
AUTH_SESSION_RATE_LIMIT=3/minute
AUTH_TOKEN_RATE_LIMIT=10/minute
MAX_ACTIVE_STREAMS_PER_CLIENT=2
```

Rate limiting uses the maintained `limits` library with in-memory storage. This is appropriate for the current single-instance deployment path. If the API is deployed across multiple instances, move rate-limit state to shared storage such as Redis.

HTTP API errors use a stable structured shape:

```json
{
  "error": {
    "status": 429,
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded."
  }
}
```

Validation errors use the same envelope with safe field-level details:

```json
{
  "error": {
    "status": 422,
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "details": [
      {
        "field": "turnstile_token",
        "message": "Field required"
      }
    ]
  }
}
```

Validation responses intentionally omit raw input values.

Internally, API-facing failures extend a common `AppError` base class with `status_code`, `code`, and `message`. This keeps route handlers from inventing one-off response shapes as new errors are added.

Frontend clients should branch on `error.code`, not raw message text.

## Browser Auth

The auth flow is designed as a generic browser-safe contract for public portfolio or SaaS-style clients:

1. Frontend tries `POST /auth/token` with `credentials: "include"`.
2. If no valid refresh cookie exists, frontend runs Cloudflare Turnstile.
3. Frontend calls `POST /auth/session` with `{ "turnstile_token": "..." }`.
4. Backend verifies Turnstile and sets a refresh token in an `HttpOnly` cookie.
5. Frontend calls `POST /auth/token` again.
6. Backend reads the refresh cookie and returns `{ "access_token": "...", "expires_in": 60 }`.
7. Frontend sends `Authorization: Bearer <access_token>` to `/prompt` and `/prompt/stream`.

This keeps the longer-lived refresh token out of JavaScript while avoiding ambient cookie auth on expensive assistant endpoints. The access token is short-lived and frontend-managed in memory.

Auth settings:

```powershell
REQUIRE_AUTH=false
AUTH_SIGNING_SECRET=
AUTH_REFRESH_TTL_SECONDS=1800
AUTH_ACCESS_TTL_SECONDS=60
AUTH_REFRESH_COOKIE_NAME=refresh_token
AUTH_COOKIE_SAMESITE=none
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_PATH=/auth
AUTH_COOKIE_DOMAIN=
AUTH_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
TURNSTILE_SECRET_KEY=
TURNSTILE_BYPASS=false
```

`TURNSTILE_BYPASS=true` is for local development only. Do not enable it in production.

## Current Limitation

Resume PDF loading is still supported through explicit local-file overrides, but PDF/DOCX ingestion into the vector store is intentionally deferred.

The streaming implementation emits these SSE events:

- `session_started`
- `progress`
- `answer_chunk`
- `answer_completed`
- `error`

It reuses the existing prompt runner and session handling. The current version streams real `generate_answer` model output from the graph as it arrives, emits stable `progress` milestones for important graph steps, lightly buffers tiny token fragments into more natural text chunks, and then sends final response metadata when the run completes.
