# LangGraph Portfolio Assistant - Prioritized Phase Build Plan

Legend:
- `[ ]` Not started
- `[x]` Done
- `MUST` Required for the phase goal
- `SHOULD` Important improvement
- `NICE` Useful later

---

## Phase 0 - Foundation

- MUST [x] Create separate project/repo
- MUST [x] Initialize Git repository
- MUST [x] Setup Python env + install deps with `uv`
- MUST [x] Basic FastAPI app runs
- SHOULD [x] Clean folder structure
- NICE [x] Add README + env template
- NICE [x] Add CLI transport for quick local testing
- NICE [x] Add project-specific architecture decision doc

Status: complete.

Notes:
- FastAPI app is available through `app.main:app`.
- CLI is available through `uv run portfolio-assistant`.
- LangGraph implementation architecture is tracked in `LANGGRAPH_ARCHITECTURE.md`.

---

## Phase 1 - Minimal Graph

- MUST [x] Define `PortfolioState`
- MUST [x] Build minimal LangGraph `StateGraph`
- MUST [x] `ingest_user_message` node
- MUST [x] `classify_relevance` node
- MUST [x] `generate_answer` node
- MUST [x] Conditional routing
- SHOULD [x] `resolve_context` node
- SHOULD [x] History-aware query contextualization without brittle trigger phrase matching
- SHOULD [x] Explicit route categories: `portfolio_query`, `off_topic`
- NICE [x] Friendly response refinement
- NICE [x] File-backed prompt templates under `app/prompts/`
- NICE [x] Unit tests for graph route behavior

Status: complete for Phase 1.

Notes:
- Real OpenAI calls are wired through `langchain-openai`.
- Graph behavior is tested with a fake assistant service, so unit tests do not require API keys.
- `resolve_context` rewrites follow-up questions when prior messages exist, matching the history-aware retrieval pattern used in conversational RAG.
- CLI smoke checks confirmed:
  - `"who are you"` routes through resume retrieval
  - user debugging requests route to `friendly_response`
  - portfolio-fit questions route to `generate_answer`

---

## Phase 2 - Retrieval Planning

- MUST [x] `plan_retrieval` node
- MUST [x] Define source categories: projects, resume, docs
- MUST [x] Routing logic works for multiple prompt types
- SHOULD [x] Add richer intent/source planning through structured OpenAI output
- SHOULD [ ] Define required user inputs: GitHub owner, resume, preferred display name
- NICE [x] Debug output for source selection through CLI/API response fields

Status: complete for planning-only Phase 2.

Notes:
- Portfolio queries now route through `plan_retrieval` before `generate_answer`.
- `PromptResponse` exposes `retrieval_sources` and `retrieval_reason`.
- No actual retrieval is performed yet; Phase 3 will add source-specific retrieval nodes.

---

## Phase 3 - Retrieval Nodes

- MUST [x] `retrieve_projects` node
- MUST [x] `retrieve_resume` node
- MUST [x] `retrieve_docs` node
- MUST [x] Support multi-source queries
- SHOULD [x] Service layer separation
- SHOULD [x] GitHub retrieval uses configured token/owner
- NICE [ ] Optional web retrieval

Status: complete for first retrieval-node implementation.

Notes:
- `projects` uses GitHub REST API and best-effort README enrichment.
- Named project queries focus retrieval on the matching repository and use a larger README excerpt budget for deeper project-specific answers.
- Featured project metadata is loaded from `portfolio/featured_projects.json` by default and is used for subjective project preference questions.
- Resume retrieval now uses Neon pgvector when `NEON_DATABASE_URL_STRING` is configured.
- CLI supports `--resume-path` as a one-off local-file override.
- PDF-to-Markdown conversion helper exists in `scripts/convert_resume_pdf.py`.
- PDF/DOCX ingestion into the vector store is intentionally deferred.

---

## Phase 4 - Context Merge

- MUST [x] `merge_normalize_context` node
- MUST [x] Combine multi-source results
- MUST [x] Prevent context overload with `MERGED_CONTEXT_MAX_CHARS`
- SHOULD [x] Replace sequential no-op retrieval chain with conditional fan-out / dynamic sends
- SHOULD [ ] Deduplication
- NICE [ ] Advanced ranking/scoring

Status: basic merge and conditional fan-out complete. Ranking/deduplication remain future work.

---

## Phase 5 - Answer Generation

- MUST [x] `generate_answer` node exists
- MUST [x] No-hallucination rule for Phase 1 inline context
- MUST [x] Handle missing data by saying context is insufficient
- MUST [x] Ground answers in retrieved multi-source context
- SHOULD [ ] Structured output formatting
- NICE [ ] Tone/UX improvements

Status: partially complete. Phase 1 grounding exists; retrieval-grounded answer generation remains.

---

## Phase 6 - Memory

- MUST [x] Messages accepted in state
- MUST [x] Interactive CLI keeps in-process conversation history for one running session
- MUST [x] Context resolver uses a bounded 4-turn history window for multi-turn references
- MUST [x] Define API session contract (`session_id`, create/reuse semantics, request/response shape)
- MUST [x] Persist and load conversation history by `session_id` for API requests
- MUST [x] `save_memory` node
- MUST [x] History trimming
- MUST [x] Wire stored history into graph invocation before `resolve_context`
- SHOULD [x] Context-aware responses from provided session history
- SHOULD [x] Skip context-resolution LLM calls for clearly standalone questions inside an active session
- SHOULD [x] API `session_id` support for stored session history
- SHOULD [x] Start with a simple app-level session store before introducing heavier memory infrastructure
- SHOULD [x] LangGraph checkpointer evaluation for persisted thread memory
- SHOULD [x] Decide when to adopt LangGraph checkpointers after the session contract is stable
- NICE [ ] Advanced memory strategies

Status: complete for current scope. The graph now owns `save_memory`, the API supports `session_id`, standalone queries skip unnecessary context-resolution LLM calls, and the app persists bounded session history in-process. LangGraph checkpointers were evaluated and intentionally deferred for this project stage.

Current implemented contract:
- request: optional `session_id`
- response: always include `session_id`
- omitted `session_id` means create a new session
- unknown or expired `session_id` should surface as a session error, not silently fork a new conversation

Checkpointer decision:
- keep the current app-level session store for now
- do not adopt LangGraph checkpointers in this repo yet
- revisit checkpointers only if we need durable sessions across restarts, multi-instance/shared memory, human-in-the-loop interrupt/resume, or broader graph-state persistence than bounded chat history

Long-term memory decision:
- do not add persistent visitor/user memory until there is a clearly defined product workflow that needs it
- current short-term session memory is enough for contextual follow-ups
- use explicit curated portfolio metadata for owner-controlled facts such as featured projects, proud-project rationale, and preferred positioning
- revisit long-term visitor memory only after auth/frontend requirements define identity, consent, clear-memory/delete behavior, and actual user value

---

## Phase 7 - FastAPI Integration

- MUST [x] `POST /prompt` route
- MUST [x] Graph invocation works
- MUST [x] Basic error handling
- SHOULD [x] Logging
- NICE [x] Config management with `pydantic-settings`

Status: mostly complete for non-streaming Phase 1 API.

---

## Phase 8 - Streaming

- MUST [x] Add separate streaming route (`POST /prompt/stream`)
- MUST [x] Reuse existing prompt runner / session flow for streaming transport
- SHOULD [x] SSE integration
- SHOULD [x] Stream true token-level answer output
- NICE [x] Stable progress events for key graph milestones
- NICE [ ] Exhaustive node-level streaming events

Status: partially complete. The current streaming cut adds an SSE route with `session_started`, `progress`, `answer_chunk`, `answer_completed`, and `error` events while reusing the existing prompt runner and session handling. Answer chunks now come from real graph/LLM streaming in the `generate_answer` step, `progress` events expose stable milestones such as context resolution and retrieval planning, and tiny token fragments are buffered into more natural chunks. Exhaustive node-level event streaming remains future work.

---

## Phase 9 - Observability

- MUST [x] Basic graph node and route logging
- SHOULD [x] Request/session correlation across API and graph logs
- SHOULD [x] Node-level tracing
- SHOULD [x] Optional structured JSON logging
- SHOULD [x] Log LLM token usage per node and aggregate total for each graph run
- SHOULD [x] Reduce suggestion-generation input tokens by deriving prompts from the grounded answer instead of resending full retrieved context
- NICE [ ] LangSmith integration

Status: partially complete. Local logging exists with request/session-aware API and graph correlation, JSON logging is available as an opt-in mode, LLM-backed graph nodes log token usage when provider metadata is available, and suggestion generation avoids a second full-context pass. External tracing remains future work.

---

## Phase 10 - Reliability

- MUST [x] Retry mechanism
- MUST [x] Graceful failure handling
- SHOULD [x] Partial responses
- NICE [ ] Advanced fallback strategies

Status: partially complete. OpenAI-backed graph steps now use configurable timeout and retry settings, `/prompt` maps upstream AI failures to `503`, and `/prompt/stream` emits structured `error` events for upstream failures while preserving `partial_answer` when output was already streamed. Richer fallback strategies remain open.

---

## Phase 11 - Comparison

- MUST [x] Compare with current system
- MUST [x] Identify strengths/weaknesses
- SHOULD [ ] Performance comparison
- NICE [ ] Write final conclusions

Status: initial architecture comparison complete.

Notes:
- The LangGraph implementation is stronger for orchestration because graph state, route decisions, retrieval planning, retrieval execution, context merge, answer generation, and memory are explicit and testable.
- Production hardening should be implemented directly in this LangGraph-native backend: auth, rate limiting, public endpoint protection, and deployment security.
- Do not introduce an MCP client/server split in this repo for now. Keep orchestration LangGraph-native.
- Keep production hardening frontend-agnostic so the backend can support a portfolio UI first and a user-centric SaaS product later.

---

## Phase 12 - Resume Embeddings And Vector Retrieval

- MUST [x] Add Neon Postgres + pgvector schema for resume documents and chunks
- MUST [x] Define deterministic resume ingestion output for vector indexing
- MUST [x] Chunk resume into stable sections suitable for retrieval
- MUST [x] Promote raw resume labels into semantic Markdown headings before chunking
- MUST [x] Generate embeddings through an explicit offline ingestion script
- MUST [x] Make ingestion idempotent using document and chunk content hashes
- MUST [x] Support dry-run and force-rebuild ingestion modes
- MUST [x] Retrieve top-k resume chunks for resume-related questions
- MUST [x] Require indexed resume vectors for normal configured resume retrieval
- SHOULD [x] Add tests for chunking and no-result behavior
- SHOULD [ ] Add integration tests for idempotency and stale chunk cleanup
- NICE [ ] Extend the same ingestion pattern to docs and case studies later

Status: complete for current resume RAG scope. Integration coverage for database idempotency and stale cleanup remains a future hardening task.

Notes:
- Initial offline indexing foundation is implemented. Live graph retrieval uses pgvector top-k chunks when `NEON_DATABASE_URL_STRING` is configured, while explicit `resume_path` remains a local-file override for development.
- Resume chunking is section-aware. Do not build a separate deterministic section router unless there is a clear short-term need.
- Ingestion should be offline for both local development and production. Do not index embeddings during API server startup.
- The API server should serve requests from an already-indexed vector store and should not perform heavy indexing work in the request or startup path.
- Use Neon Postgres with pgvector for the first implementation unless a blocker appears.
- Do not add optional RAG/bootstrap feature flags for normal operation. Missing vectors are surfaced as setup/configuration failure when vector retrieval is configured.
- The first implementation should stay simple: explicit indexing script, deterministic chunking, idempotent upserts, small top-k retrieval.

---

## Phase 13 - Public Production Hardening

- MUST [x] Add deterministic policy guard before relevance classification
- MUST [x] Add route-level rate limiting for `/prompt` and `/prompt/stream`
- MUST [x] Add streaming concurrency protection
- MUST [x] Add public auth gate suitable for a portfolio site
- MUST [x] Add browser-friendly auth flow before enabling auth in production
- MUST [x] Add secure CORS/origin policy for public deployment
- MUST [x] Hide development-only docs/routes in production where appropriate
- MUST [x] Ensure client-visible errors do not leak internal service details
- SHOULD [x] Add request abuse logging and rate-limit hit logging
- SHOULD [x] Add security-focused tests around auth, rate limits, and streaming errors
- NICE [ ] Move rate-limit/session state to shared storage if deploying more than one instance

Status: planned for public replacement readiness.

Notes:
- `policy_guard` now blocks prompt injection, hidden prompt extraction, fake portfolio fabrication, secret/credential requests, and harmful-content requests before retrieval or answer generation.
- Manual jailbreak smoke checks confirmed unsafe prompts now short-circuit at `policy_guard`, while normal portfolio queries continue through classification, retrieval, merge, and answer generation.
- `/prompt` and `/prompt/stream` now use the maintained `limits` library for configurable in-process request rate limiting.
- `/prompt/stream` also has an active-stream concurrency guard to protect long-running SSE responses.
- HTTP API errors now use a stable `{error: {status, code, message}}` shape so clients can branch on error codes.
- FastAPI validation and framework HTTP errors are normalized globally; validation details expose only `field` and `message`, never raw input.
- API-facing errors now extend a common `AppError` base class so status codes, machine-readable error codes, and safe messages are owned by typed errors instead of duplicated in route handlers.
- `APP_ENV=production` disables `/docs`, `/redoc`, and `/openapi.json`; local development keeps them enabled by default.
- Auth implementation target: provide a generic browser-safe contract for public clients.
  `POST /auth/session` verifies Cloudflare Turnstile and sets an HttpOnly refresh cookie.
  `POST /auth/token` reads that refresh cookie and returns a short-lived access token.
  `/prompt` and `/prompt/stream` require `Authorization: Bearer <access_token>` only when `REQUIRE_AUTH=true`.
- Auth design decisions:
  use a maintained JWT library for signed refresh/access tokens, keep access tokens in frontend memory, keep the refresh token in an HttpOnly cookie, and keep expensive endpoints explicit-bearer-token authenticated rather than ambient-cookie authenticated.
- Turnstile remains the first human-verification gate. A future identity provider such as GitHub OAuth can later replace or augment the session bootstrap while preserving the same app-owned refresh/access token model.
- Auth routes now use structured API errors, origin allowlisting, dedicated auth rate limits, 32+ byte HMAC signing secret validation, and async Turnstile verification.
- Auth is required before public production deployment because the API can incur real OpenAI/GitHub cost.
- Keep this separate from orchestration work so the graph remains simple and testable.

---

## Phase 14 - Frontend Integration

- MUST [ ] Build or adapt a React client against the LangGraph API contract
- MUST [ ] Implement non-streaming `/prompt` adapter for the LangGraph response shape
- MUST [ ] Implement `/prompt/stream` SSE adapter for LangGraph event names
- MUST [ ] Map backend progress events to safe user-facing status labels
- MUST [ ] Preserve `session_id` reuse for follow-up questions
- MUST [ ] Hide raw graph internals from the public UI
- SHOULD [ ] Implement browser auth client for `/auth/session`, `/auth/token`, and bearer-token prompt calls
- SHOULD [ ] Add a debug-only mode for traces and retrieval metadata
- NICE [ ] Keep UI implementation decoupled enough to support future SaaS onboarding and account flows

Status: planned.

Notes:
- Frontend migration details live in `FRONTEND_MIGRATION_PLAN.md`.
- Do not rebuild the frontend from scratch. The goal is an API contract migration, not a UX rewrite.
- Public UI should show friendly work states, not internal graph node names or retrieval planner details.

---

## Future SaaS Direction

Status: documented for later, not part of the current backend hardening scope.

Notes:
- Longer-term SaaS direction lives in `SAAS_READINESS_PLAN.md`.
- Do not build billing, multi-user onboarding, resume upload, or GitHub OAuth before the public security hardening phase is complete.
- The immediate priority remains making this backend safe and stable enough for public deployment.

---

## Smartness Roadmap

This section tracks capability upgrades that make the agentic assistant materially smarter without adding unnecessary orchestration complexity.

Guiding principle:
- prefer better retrieval quality and evidence selection before adding heavier agent loops or memory systems
- keep orchestration LangGraph-native for now; do not introduce MCP unless a clear tool/plugin boundary becomes necessary

### Near-Term: High Impact, Lower Complexity

- SHOULD [x] Enrich `projects` retrieval with README content
- SHOULD [x] Add featured project detail
- SHOULD [x] Add in-memory TTL caching for GitHub repository and README retrieval
- SHOULD [x] Add deterministic fuzzy repo-name matching for clear project-name typos
- SHOULD [ ] Add relevance scoring/ranking so project answers prefer the best-matching projects instead of mostly recent repositories
- SHOULD [x] Add resume section-aware chunking in the resume embeddings/vector phase
- SHOULD [x] Add clarification behavior for ambiguous follow-up questions instead of guessing

Expected value:
- improves answer quality directly
- makes project and skills answers feel much smarter without changing the graph shape much

### Mid-Term: High Impact, Moderate Complexity

- SHOULD [ ] Park deduplication/evidence selection until retrieval volume makes context noise a real problem
- SHOULD [x] Add deeper project drill-down retrieval for one selected repository
- SHOULD [ ] Support query-specific source expansion when one source is clearly insufficient
- SHOULD [ ] Add structured answer modes for concise vs detailed responses

Expected value:
- improves depth, evidence quality, and consistency
- makes the assistant better at project-specific discussion instead of only broad summaries

### Later: Advanced Capability Upgrades

- NICE [x] Add resume embeddings and vector retrieval
- NICE [ ] Add richer long-form docs ingestion and selective RAG for larger document sets
- NICE [ ] Add entity/topic memory beyond bounded chat history
- NICE [ ] Add evaluation datasets for answer quality and retrieval quality
- NICE [ ] Add external tracing/evaluation tooling such as LangSmith when local observability is no longer enough
- NICE [ ] Explore deeper agent/tool behaviors only after retrieval quality is strong

Expected value:
- improves scale, long-term maintainability, and systematic quality measurement
- should be sequenced after retrieval quality improvements, not before them

### Recommended Implementation Order

1. Project relevance scoring/ranking
2. Structured answer modes for concise vs detailed responses
3. Performance baseline against current public behavior
4. Public production hardening: auth, rate limits, CORS, streaming abuse protection
5. Frontend integration against the LangGraph backend
6. Larger-doc RAG only when needed

---

## Success Criteria

- MUST [x] End-to-end minimal graph works
- MUST [ ] Multi-source answers work
- MUST [x] Follow-ups work with real session memory
- SHOULD [ ] Streaming works
- NICE [ ] Observability + reliability layers added
