---
name: optimize
description: Use when improving performance, latency, cost, memory usage, or scalability.
---

# Optimize Skill

## Goal

Improve performance without reducing correctness or readability.

## Steps

1. Identify the bottleneck
2. Measure or reason about the current cost
3. Choose the simplest optimization
4. Preserve existing behavior
5. Validate improvement
6. Avoid unnecessary complexity

## Rules

- Do not optimize blindly
- Do not sacrifice readability for minor gains
- Prefer caching, batching, indexing, or reducing repeated work where appropriate
- Avoid premature optimization
- Explain the tradeoff

## Final Check

- What was the bottleneck?
- What changed?
- Why is it faster or cheaper?
- Did behavior remain the same?