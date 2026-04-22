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
- Old-system reference architecture is preserved in `ARCHITECTURE_OLD_SYSTEM.md`.
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
- SHOULD [x] Explicit route categories: `portfolio_query`, `assistant_identity`, `off_topic`
- SHOULD [x] Dedicated `assistant_intro` node
- NICE [x] Friendly response refinement
- NICE [x] File-backed prompt templates under `app/prompts/`
- NICE [x] Unit tests for graph route behavior

Status: complete for Phase 1.

Notes:
- Real OpenAI calls are wired through `langchain-openai`.
- Graph behavior is tested with a fake assistant service, so unit tests do not require API keys.
- CLI smoke checks confirmed:
  - `"who are you"` routes to `assistant_intro`
  - user debugging requests route to `friendly_response`
  - portfolio-fit questions route to `generate_answer`

---

## Phase 2 - Retrieval Planning

- MUST [x] `plan_retrieval` node
- MUST [x] Define source categories: profile, projects, resume, work_history, docs
- MUST [x] Routing logic works for multiple prompt types
- SHOULD [x] Add richer intent/source planning through structured OpenAI output
- SHOULD [ ] Define required user/profile inputs: GitHub owner, resume, work history, preferred display name
- NICE [x] Debug output for source selection through CLI/API response fields

Status: complete for planning-only Phase 2.

Notes:
- Portfolio queries now route through `plan_retrieval` before `generate_answer`.
- `PromptResponse` exposes `retrieval_sources` and `retrieval_reason`.
- No actual retrieval is performed yet; Phase 3 will add source-specific retrieval nodes.

---

## Phase 3 - Retrieval Nodes

- MUST [ ] `retrieve_projects` node
- MUST [ ] `retrieve_resume` node
- MUST [ ] `retrieve_docs` node
- MUST [ ] Support multi-source queries
- SHOULD [ ] Service layer separation
- SHOULD [ ] GitHub retrieval uses configured token/owner
- NICE [ ] Optional web retrieval

---

## Phase 4 - Context Merge

- MUST [ ] `merge_normalize_context` node
- MUST [ ] Combine multi-source results
- MUST [ ] Prevent context overload
- SHOULD [ ] Deduplication
- NICE [ ] Advanced ranking/scoring

---

## Phase 5 - Answer Generation

- MUST [x] `generate_answer` node exists
- MUST [x] No-hallucination rule for Phase 1 inline context
- MUST [x] Handle missing data by saying context is insufficient
- MUST [ ] Ground answers in retrieved multi-source context
- SHOULD [ ] Structured output formatting
- NICE [ ] Tone/UX improvements

Status: partially complete. Phase 1 grounding exists; retrieval-grounded answer generation remains.

---

## Phase 6 - Memory

- MUST [x] Messages accepted in state
- MUST [ ] `save_memory` node
- MUST [ ] History trimming
- SHOULD [ ] Context-aware responses from stored session history
- NICE [ ] Advanced memory strategies

Status: partially complete. State accepts history for context resolution, but persistent/session memory is not implemented.

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

- MUST [ ] Basic logging
- SHOULD [ ] Node-level tracing
- NICE [ ] LangSmith integration

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
