---
title: MCP With Codex
description: Configure OntoMCP for Codex-based local workflows
---

## Install

Install the runtime first:

```bash
npx ontoskills install mcp
npx ontoskills install mcp --codex
```

This installs:

```text
~/.ontoskills/bin/ontomcp
```

## Fast Bootstrap

The recommended setup is:

```bash
npx ontoskills install mcp --codex
```

Manual equivalent:

```bash
codex mcp add ontomcp -- ~/.ontoskills/bin/ontomcp
```

Codex global setup uses the same local `stdio` command as other clients:

```text
~/.ontoskills/bin/ontomcp
```

## Tools Exposed

- `search_skills`
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`
- `search_intents`

## Notes

- The MCP server reads compiled `.ttl` ontologies, not raw `SKILL.md`
- If you want custom skills, install the compiler too:

```bash
npx ontoskills install core
```

- Then compile or import source skills — they are auto-enabled on install for MCP access
- `--codex` automates Codex global setup only; for repository-local Codex MCP config, `ontoskills` currently prints manual steps instead of forcing a non-standard config file
