---
name: debug
description: Use when investigating, reproducing, and fixing bugs.
---

# Debug Skill

## Goal

Find the root cause and fix the bug safely.

## Steps

1. Reproduce the issue
2. Identify the failing path
3. Write or update a test that captures the bug
4. Fix the smallest necessary part
5. Verify the bug is fixed
6. Check for regressions

## Rules

- Do not guess the fix without evidence
- Do not rewrite large areas unless necessary
- Prefer root-cause fixes over patches
- Explain the cause clearly

## Final Check

- Was the bug reproduced?
- Is the root cause understood?
- Is the fix minimal?
- Is there a test covering it?