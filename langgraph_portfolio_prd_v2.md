# LangGraph Portfolio Assistant (Implementation Plan - Python First)

## Overview
This document outlines a step-by-step implementation plan to build a LangGraph-based version of the portfolio assistant.

Goal:
- Learn LangGraph deeply
- Recreate current system behavior using explicit graph orchestration
- Keep production system untouched

---

## Architecture Decision

Use:

Python + FastAPI + LangGraph (Graph API)

Reason:
- Existing system already in Python
- LangGraph ecosystem strongest in Python
- Easier comparison with current architecture

---

## Phase 0: Setup

Project structure:

langgraph-portfolio/
├── app/
│   ├── main.py
│   ├── graph/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── routing.py
│   │   └── builder.py
│   ├── services/
│   ├── prompts/
│   └── api/
├── tests/
└── requirements.txt

Install:
pip install fastapi uvicorn langgraph langchain openai

---

## Phase 1: Minimal Graph

Nodes:
- ingest_user_message
- resolve_context
- classify_relevance
- retrieve_context
- generate_answer
- friendly_response

Flow:

START
  ↓
ingest_user_message
  ↓
resolve_context
  ↓
classify_relevance
  ├── irrelevant → friendly_response → END
  └── relevant → retrieve_context → generate_answer → END

Goal:
- Learn state + node execution
- Implement conditional edges

---

## Phase 2: Structured Retrieval

Add nodes:
- plan_retrieval
- retrieve_projects
- retrieve_resume
- retrieve_docs
- merge_normalize_context
- save_memory

Flow:

START
  ↓
ingest_user_message
  ↓
resolve_context
  ↓
classify_relevance
  ├── irrelevant → friendly_response → END
  └── relevant → plan_retrieval
                     ↓
        retrieve_projects / resume / docs
                     ↓
        merge_normalize_context
                     ↓
        generate_answer
                     ↓
        save_memory
                     ↓
                     END

Goal:
- Multi-source retrieval
- Clean orchestration

---

## Phase 3: Memory

State includes:
- messages
- recent history (bounded)

Add:
- session-level memory
- trimming logic

Future:
- LangGraph checkpointer

---

## Phase 4: Streaming

Steps:
1. Normal response
2. Stream final answer
3. Stream node progress (optional)

Keep FastAPI for:
- transport
- SSE

---

## Phase 5: Observability

Add LangSmith:
- trace nodes
- inspect LLM calls
- debug execution paths

Track:
- node inputs/outputs
- latency
- errors

---

## Phase 6: Reliability

Add:
- retry logic
- fallback paths
- timeout handling
- partial responses

Example:

retrieve_projects
  ├── success → continue
  └── failure → skip + continue

---

## State Design

PortfolioState:

- user_query
- rewritten_query
- messages
- is_relevant
- intent
- retrieval_sources
- project_hits
- resume_hits
- doc_hits
- merged_context
- final_answer
- error

---

## Node Responsibilities

ingest_user_message:
- capture input

resolve_context:
- rewrite ambiguous queries

classify_relevance:
- detect intent

plan_retrieval:
- choose sources

retrieval nodes:
- fetch data

merge_normalize_context:
- combine results

generate_answer:
- synthesize response

save_memory:
- store history

---

## Milestones

1. Basic graph works
2. Conditional routing works
3. Multi-source retrieval works
4. Context merging works
5. Memory works
6. Streaming works
7. Observability added
8. Reliability added

---

## Key Learning Outcomes

- Understand LangGraph state model
- Learn node-based orchestration
- Compare workflow vs agents
- Build production-ready AI architecture mindset

---

## Final Recommendation

Do NOT replace current system.

Build this as:
- parallel system
- learning environment

Later decide:
- whether to merge
- or keep both architectures
