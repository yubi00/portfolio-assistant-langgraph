---
name: refactor
description: Use when improving code structure, readability, or maintainability without changing behavior.
---

# Refactor Skill

## Goal

Improve code quality without changing external behavior.

## Steps

1. Identify the current behavior
2. Preserve existing tests
3. Refactor in small, safe steps
4. Remove duplication
5. Improve naming and structure
6. Re-run validation

## Rules

- Do not change behavior
- Do not add new features
- Do not refactor unrelated code
- Keep diffs focused
- Prefer readability over cleverness

## Final Check

- Does behavior remain the same?
- Are changes easier to understand?
- Is the diff focused?
- Did any unrelated code change?