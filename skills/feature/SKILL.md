---
name: feature
description: Use when adding a new feature or behavior to the codebase.
---

# Feature Implementation Skill

## Goal

Add the requested feature with minimal, clean, maintainable changes.

## Steps

1. Understand the requested behavior
2. Identify the smallest implementation path
3. Follow existing project structure and patterns
4. Add or update tests for the new behavior
5. Verify existing behavior still works

## Rules

- Do not add unrelated features
- Do not introduce new dependencies unless clearly justified
- Keep routes/controllers thin
- Keep business logic in the appropriate layer
- Prefer simple implementation first

## Final Check

- Does the feature meet the requested behavior?
- Are tests added or updated?
- Are changes minimal?
- Is the code easy to understand?