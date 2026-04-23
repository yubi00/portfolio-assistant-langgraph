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
- SHOULD [x] Explicit route categories: `portfolio_query`, `assistant_identity`, `off_topic`
- SHOULD [x] Dedicated `assistant_intro` node
- NICE [x] Friendly response refinement
- NICE [x] File-backed prompt templates under `app/prompts/`
- NICE [x] Unit tests for graph route behavior

Status: complete for Phase 1.

Notes:
- Real OpenAI calls are wired through `langchain-openai`.
- Graph behavior is tested with a fake assistant service, so unit tests do not require API keys.
- `resolve_context` rewrites follow-up questions when prior messages exist, matching the history-aware retrieval pattern used in conversational RAG.
- CLI smoke checks confirmed:
  - `"who are you"` routes to `assistant_intro`
  - user debugging requests route to `friendly_response`
  - portfolio-fit questions route to `generate_answer`

---

## Phase 2 - Retrieval Planning

- MUST [x] `plan_retrieval` node
- MUST [x] Define source categories: profile, projects, resume, docs
- MUST [x] Routing logic works for multiple prompt types
- SHOULD [x] Add richer intent/source planning through structured OpenAI output
- SHOULD [ ] Define required user/profile inputs: GitHub owner, resume, preferred display name
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
- SHOULD [x] `retrieve_profile` node
- NICE [ ] Optional web retrieval

Status: complete for first retrieval-node implementation.

Notes:
- `projects` uses GitHub REST API.
- Work-experience answers use the `resume` source because the resume already contains employment history.
- CLI supports `--resume-path` for local testing without editing `.env`.
- PDF-to-Markdown conversion helper exists in `scripts/convert_resume_pdf.py`.
- Full PDF/DOCX ingestion and RAG are intentionally deferred.

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
- MUST [ ] `save_memory` node
- MUST [ ] History trimming
- SHOULD [x] Context-aware responses from provided session history
- SHOULD [ ] API `session_id` support for stored session history
- SHOULD [ ] LangGraph checkpointer evaluation for persisted thread memory
- NICE [ ] Advanced memory strategies

Status: partially complete. State accepts history for context resolution and the CLI keeps in-process history, but persisted API session memory is not implemented.

---

## Phase 7 - FastAPI Integration

- MUST [x] `POST /prompt` route
- MUST [x] Graph invocation works
- MUST [x] Basic error handling
- SHOULD [ ] Logging
- NICE [x] Config management with `pydantic-settings`

Status: mostly complete for non-streaming Phase 1 API.

---

## Phase 8 - Streaming

- MUST [ ] Stream final answer
- SHOULD [ ] SSE integration
- NICE [ ] Node-level streaming events

---

## Phase 9 - Observability

- MUST [x] Basic graph node and route logging
- SHOULD [ ] Node-level tracing
- NICE [ ] LangSmith integration

Status: partially complete. Local logging exists; structured logs/tracing remain future work.

---

## Phase 10 - Reliability

- MUST [ ] Retry mechanism
- MUST [ ] Graceful failure handling
- SHOULD [ ] Partial responses
- NICE [ ] Advanced fallback strategies

---

## Phase 11 - Comparison

- MUST [ ] Compare with current system
- MUST [ ] Identify strengths/weaknesses
- SHOULD [ ] Performance comparison
- NICE [ ] Write final conclusions

---

## Success Criteria

- MUST [x] End-to-end minimal graph works
- MUST [ ] Multi-source answers work
- MUST [ ] Follow-ups work with real session memory
- SHOULD [ ] Streaming works
- NICE [ ] Observability + reliability layers added
