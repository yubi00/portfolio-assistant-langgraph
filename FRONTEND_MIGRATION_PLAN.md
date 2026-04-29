# Frontend Migration Plan

This document tracks the changes needed to point the existing React terminal frontend at this LangGraph backend.

The goal is to reuse the existing `ai-portfolio` frontend instead of rebuilding the UI from scratch.

---

## Direction

- Keep the existing terminal-style React frontend.
- Replace only the backend API adapter layer when the LangGraph backend contract is stable.
- Do not expose LangGraph internals directly in the public UI.
- Keep detailed traces and retrieval metadata for debug/dev views only.

---

## Current Frontend Integration Points

Existing frontend repo:

```text
../ai-portfolio
```

Important files:

- `client/src/commands/aiHandler.ts` handles non-streaming `/prompt`.
- `client/src/hooks/useStreamingResponse.ts` handles `/prompt/stream` SSE.
- `client/src/config/env.ts` owns API URL and auth flags.
- `client/src/utils/auth/*` owns the existing auth-token flow.

These files should be enough for the first backend swap. A full frontend rewrite is not needed.

---

## API Contract Differences

### Non-Streaming Prompt

Old frontend expects:

```ts
{
  reply: string;
  session_id: string;
}
```

LangGraph backend returns:

```ts
{
  answer: string;
  session_id: string;
  history: Array<{ user: string; assistant: string }>;
  is_relevant: boolean;
  intent: string;
  route: string;
  retrieval_sources: string[];
  retrieval_reason: string;
  retrieval_errors: string[];
  rewritten_query: string;
  node_trace: string[];
}
```

Frontend should render only:

- `answer`
- `session_id`

Debug-only fields:

- `rewritten_query`
- `intent`
- `route`
- `retrieval_sources`
- `retrieval_reason`
- `retrieval_errors`
- `node_trace`

### Streaming Prompt

Old frontend event model:

```text
session
status
context
classification
partial
final
done
```

LangGraph backend event model:

```text
session_started
progress
answer_chunk
answer_completed
error
```

Frontend migration should update the SSE adapter rather than changing terminal rendering broadly.

---

## Progress UX

The frontend should show user-friendly work states, not backend node names.

Recommended mapping:

```ts
const PROGRESS_LABELS: Record<string, string> = {
  resolve_context: 'understanding your question',
  classify_relevance: 'checking portfolio relevance',
  check_ambiguity: 'clarifying intent',
  plan_retrieval: 'choosing the right sources',
  retrieve_projects: 'looking through project details',
  retrieve_resume: 'checking resume background',
  retrieve_docs: 'checking supporting notes',
  merge_normalize_context: 'preparing context',
  generate_answer: 'writing response',
};
```

Hide from public UI:

- `ingest_user_message`
- `save_memory`
- raw `node_trace`
- raw route names
- raw intent labels
- retrieval planner reasoning
- internal exception details

Error copy should be generic:

```text
I had trouble generating a response. Please try again.
```

Detailed errors should remain in backend logs and debug-only views.

---

## Session Handling

- Continue storing the returned `session_id` in frontend state.
- Reuse the same `session_id` for follow-up prompts.
- Treat missing `session_id` as a new conversation.
- Treat unknown/expired session errors as recoverable: clear the frontend session and start a new one.

---

## Auth Migration

The existing frontend already has an auth utility layer under:

```text
client/src/utils/auth/*
```

When the LangGraph backend adds public auth:

- keep the existing frontend auth flow if possible
- update endpoint assumptions only where needed
- preserve short-lived access-token behavior for expensive `/prompt*` routes
- continue avoiding token persistence in localStorage

Auth should not block the first local frontend migration. It belongs with production hardening.

---

## Local Development Changes

Current frontend local default points at:

```text
http://127.0.0.1:9000
```

LangGraph backend local default is:

```text
http://127.0.0.1:8000
```

Options:

- set `VITE_API_URL=http://127.0.0.1:8000`
- or update the frontend local default when migration starts

---

## Proposed Migration Steps

1. Add a small API response adapter for `/prompt`.
2. Update the SSE parser to support LangGraph event names.
3. Map `progress.node` to safe user-facing labels.
4. Render `answer_chunk.delta` as streamed terminal output.
5. Render `answer_completed.answer` only as fallback if no chunks were shown.
6. Store and reuse `session_id` from `session_started` and final responses.
7. Keep debug metadata hidden unless a dev/debug flag is enabled.
8. Add auth integration after backend production hardening is implemented.

---

## Backend Preconditions

Before replacing the old public backend:

- LangGraph backend is stable for `/prompt` and `/prompt/stream`.
- Public auth is implemented.
- Rate limiting and streaming concurrency protection are implemented.
- CORS/origin policy is production-ready.
- Client-visible errors are safe and generic.
- Manual frontend smoke tests pass against the new backend.
