# LangGraph Portfolio Assistant

LangGraph-powered implementation of a generic, agentic portfolio assistant.

This implementation's architecture and decision log live in `LANGGRAPH_ARCHITECTURE.md`.

## Main Features

- grounded portfolio Q&A across `projects`, `resume`, and `docs`
- history-aware contextual follow-up handling
- deterministic policy guard for prompt injection, prompt extraction, unsafe fabrication, secrets, and harmful-content requests
- clarification guard rail for genuinely ambiguous follow-up references
- one structured routing decision chooses relevance and retrieval sources before answer generation
- targeted GitHub project deep dives when a query names a specific repository
- multi-source context merge with bounded context size
- structured suggested follow-up prompts for richer portfolio conversations
- API session memory via `session_id`
- CLI and FastAPI transports backed by the same graph runner
- SSE streaming via `POST /prompt/stream`
- request/session-aware logging with optional JSON log format
- basic upstream reliability controls with retries, timeouts, and streaming partial-answer preservation
- public API abuse protection with request rate limits and active stream concurrency limits
- optional browser auth for public deployments: Turnstile bootstrap, HttpOnly refresh cookie, and short-lived bearer access tokens

## What Makes It Special

This is an agentic assistant, not just a single-prompt chatbot over a resume.

It is still intentionally bounded: it answers portfolio questions, retrieves evidence, handles follow-ups, and applies guard rails, but it does not act as a general autonomous agent that takes open-ended actions.

What makes it different:

- it uses an explicit LangGraph orchestration flow instead of burying behavior inside one prompt
- it rewrites context-dependent follow-up questions into standalone queries before planning retrieval
- it chooses the smallest useful source set before answering instead of always dumping all context into the model
- it focuses project retrieval on one named repository for deeper project-specific questions
- it has a clarification guard rail for genuinely ambiguous follow-ups instead of guessing blindly
- it returns grounded suggested follow-up prompts separately from the answer so frontends can render optional next-step chips
- it supports both request/response and SSE streaming while reusing the same core graph runner
- it keeps the architecture simple enough to extend without turning into an overengineered autonomous agent system

## Current Scope

- FastAPI application
- `uv` project setup
- LangGraph `StateGraph`
- Nodes for ingest, policy guard, context resolution, combined routing/source selection, ambiguity checking, retrieval planning, retrieval, context merge, answer generation, suggestion generation, clarification response, and friendly off-topic responses
- Conditional routing for portfolio and off-topic prompts
- Real OpenAI calls through `langchain-openai`
- File-backed system prompts under `app/prompts/`

For a portfolio question, the graph checks the original prompt against the policy guard, resolves context-dependent follow-ups, and makes one structured OpenAI call to choose both the route and retrieval sources. The `plan_retrieval` node records that decision after ambiguity checking; it does not make another model call. Selected sources are retrieved, their evidence is merged within `MERGED_CONTEXT_MAX_CHARS` (12,000 by default), and the answer is generated. Eligible answers then receive suggested follow-up prompts before the completed turn is saved. Off-topic or blocked requests take the friendly-response path without retrieval or answer generation.

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
Cold README cache misses are fetched with at most three concurrent GitHub requests; warm cache hits make no README request.

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

API session memory is available through `session_id`. Omit it on the first request, then reuse the returned `session_id` on follow-up requests.

You may provide `history` when starting a new session. Once you send a `session_id`, the API uses the history stored for that session and ignores any client-supplied `history`. This applies to both `/prompt` and `/prompt/stream` and prevents the same turns from being added twice.

Both prompt endpoints limit public input to 4,000 prompt characters, 10 submitted history turns, 24,000 characters across submitted history text, and 120 characters for an optional `assistant_subject`. Exceeding a limit returns `422 VALIDATION_ERROR` before assistant processing. Submitted history is validated even when a `session_id` means it will be ignored; clients should omit it on follow-ups. These limits do not apply to the local CLI.

Overlapping requests with the same `session_id` can run at the same time. Each answer sees the history available when its request starts; completed turns are saved in completion order so neither successful request overwrites the other. Sessions remain local to one server process. By default, the store retains the latest 10 turns (`SESSION_HISTORY_MAX_TURNS`) and expires a session after 30 minutes without access (`SESSION_TTL_MINUTES`). Context-dependent rewriting considers up to the latest 4 turns (`CONTEXT_HISTORY_WINDOW`).

The current memory model is a bounded app-level session store. LangGraph checkpointers were evaluated and intentionally deferred because this repo currently only needs short-term conversational memory, not durable thread persistence.

Long-term visitor memory is intentionally deferred until there is a clear product workflow, authenticated identity, consent, and deletion behavior. Owner-controlled facts should be represented through explicit portfolio metadata instead.

Ambiguous follow-up questions now have a lightweight clarification guard rail. If context resolution cannot safely identify one target from recent history, the assistant asks a short clarification question instead of guessing.

Streaming is available through `POST /prompt/stream` using Server-Sent Events (SSE).

```powershell
Invoke-WebRequest -Method Post http://127.0.0.1:8000/prompt/stream `
  -ContentType "application/json" `
  -Body '{"prompt":"What projects has this person built?"}'
```

The SSE endpoint emits `session_started`, `progress`, `answer_chunk`, and `answer_completed` events, or an `error` event if processing fails after streaming begins. `answer_chunk` carries incremental generated text; `answer_completed` carries the final response metadata, including `session_id`, `history`, retrieval details, and `suggested_prompts`. Suggestions are generated after the answer for eligible portfolio queries, so they may arrive noticeably later than the last answer chunk. Clients that do not use suggestions can ignore them.

Once SSE has started, an upstream failure is reported as an `error` event even though the HTTP status is already 200. Clients should treat `answer_completed` as successful completion and inspect `error` for a safe detail and any `partial_answer`. Validation, authorization, rate-limit, and unknown-session failures that occur before streaming starts use normal HTTP error responses. `Invoke-WebRequest` may buffer the response; use a streaming-capable client to observe chunks as they arrive.

## Vercel Deployment

The repo includes a root `main.py` compatibility entry point for Vercel:

```python
from app.main import app

handler = app
```

Keep local development pointed at `app.main:app`; the root file exists only so Vercel and other deployment tooling can discover the FastAPI app without moving the real application package.

Deployment files:

- `main.py` exposes `app` and `handler`
- `.python-version` pins Python 3.13
- `requirements.txt` mirrors runtime dependencies from `pyproject.toml`
- `.vercelignore` excludes local env files, caches, tests, and private resume inputs

Minimum production environment for a public deployment:

```powershell
APP_ENV=production
OPENAI_API_KEY=...
ASSISTANT_SUBJECT=...
GITHUB_OWNER=...
GITHUB_TOKEN=...
NEON_DATABASE_URL_STRING=...
REQUIRE_AUTH=true
AUTH_SIGNING_SECRET=...
AUTH_ALLOWED_ORIGINS=https://your-frontend.example
TURNSTILE_SECRET_KEY=...
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=none
TURNSTILE_BYPASS=false
```

Run `portfolio-index-resume` offline before expecting resume answers from pgvector in production. The API does not create embeddings during server startup.

Deployment caveat: the Vercel production app can run on separate function instances. Session history, rate limits, active-stream counts, and GitHub caches currently live only in each instance's memory. A later request may lose its session after an instance change or cold start; limits are not global, and caches may warm independently. Shared sessions and global limits are deferred while traffic is low, not guaranteed by this deployment. See the Bite 12 decision in `LANGGRAPH_ARCHITECTURE.md` before relying on durable follow-ups or global limits.

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

LLM-backed nodes log token usage when the provider response includes it. Logs include input, output, and total tokens per node, and the final `save_memory` node logs the aggregate token total for the graph run.

JSON logging is opt-in. The default remains colorized text logs for local development.

## Reliability

The app now applies basic reliability controls to OpenAI-backed graph steps:

- configurable request timeout with `OPENAI_TIMEOUT_SECONDS`
- configurable client retries with `OPENAI_MAX_RETRIES`
- non-streaming `/prompt` returns `503` for upstream AI-service failures
- streaming `/prompt/stream` emits an `error` SSE event with a safe upstream failure message after streaming has started
- when a stream fails after partial output, the `error` event includes `partial_answer`

## Public API Protection

The API applies lightweight in-process abuse protection:

- production mode hides development-only API docs when `APP_ENV=production`
- `/prompt` rate limit via `PROMPT_RATE_LIMIT`
- `/prompt/stream` rate limit via `PROMPT_STREAM_RATE_LIMIT`
- `/auth/session` rate limit via `AUTH_SESSION_RATE_LIMIT`
- `/auth/token` rate limit via `AUTH_TOKEN_RATE_LIMIT`
- active SSE stream concurrency limit via `MAX_ACTIVE_STREAMS_PER_CLIENT`

Defaults:

```powershell
APP_ENV=development
RATE_LIMIT_ENABLED=true
PROMPT_RATE_LIMIT=30/minute
PROMPT_STREAM_RATE_LIMIT=10/minute
AUTH_SESSION_RATE_LIMIT=3/minute
AUTH_TOKEN_RATE_LIMIT=10/minute
MAX_ACTIVE_STREAMS_PER_CLIENT=2
TRUST_PROXY_HEADERS=false
```

Set `APP_ENV=production` in public deployments to disable `/docs`, `/redoc`, and `/openapi.json`.
Production startup also requires `REQUIRE_AUTH=true` and `TURNSTILE_BYPASS=false`; the app returns a configuration error if either guard is violated.

Rate limiting uses the maintained `limits` library with in-memory storage. By default, client identity comes from the direct request client address and ignores spoofable forwarded headers. Set `TRUST_PROXY_HEADERS=true` only when the API is reachable exclusively through a trusted proxy that sanitizes `X-Forwarded-For`. If the API is deployed across multiple instances, move rate-limit state to shared storage such as Redis.

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

## Tests

```powershell
uv run pytest -q
```

The test suite uses fakes for external services. To verify the full request path, run the API locally and call `/prompt/stream` with working OpenAI, GitHub, and Neon configuration; this makes live requests and may incur provider charges.
