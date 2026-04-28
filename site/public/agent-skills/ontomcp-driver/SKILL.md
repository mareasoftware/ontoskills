---
name: ontomcp-driver
description: Use OntoSkills MCP tools to discover and apply structured skill knowledge.
---

## Tools

- **prefetch_knowledge** — One call: search + fetch context + compact. **Use this first.**
- **search** — Find skills by keyword, alias, or structured filters.
- **get_skill_context** — Full skill context with knowledge nodes (procedures, constraints, anti-patterns).
- **evaluate_execution_plan** — Validate a multi-skill plan against state chains.
- **query_epistemic_rules** — Cross-skill knowledge rules filtered by kind/severity.

Responses are compact by default. Use `format: "raw"` for full JSON.

## Workflow

1. Call `prefetch_knowledge` with a query describing the task goal.
2. Read the returned knowledge nodes — they contain procedures, constraints, and anti-patterns.
3. For multi-skill plans: call `evaluate_execution_plan` to validate state chains.
4. Write code following the knowledge nodes.

## Critical rules

- **Always prefetch first** — don't guess skill names.
- **CRITICAL/HIGH severity nodes are hard constraints** — never skip them.
- **Check requiresState** — skills fail without their preconditions.

## State semantics

Skills form a state machine: `requiresState` (preconditions) / `yieldsState` (outcomes).
Skill A's yieldsState must match Skill B's requiresState for valid chaining.
