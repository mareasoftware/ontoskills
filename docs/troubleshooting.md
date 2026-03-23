---
title: Troubleshooting
description: Common issues with installs, store access, compiler setup, and OntoMCP
---

## `ontoskills install mcp` fails

Check:

- Node.js is available
- the release artifacts for the current version exist
- your machine can download GitHub release assets

## Store skill does not appear in OntoMCP

Most often the skill was installed but not enabled:

```bash
ontoskills enable mareasw/greeting/hello
```

If it is already enabled, rebuild the local indexes:

```bash
ontoskills rebuild-index
```

Then restart the MCP process.

## Compiler commands fail

Install the compiler first:

```bash
ontoskills install core
```

Then initialize the ontology foundation:

```bash
ontoskills init-core
```

## Imported source repo compiled, but the skill still is not visible

Imported source skills also need enablement:

```bash
ontoskills enable <qualified-id>
```

## Reset Everything

To remove the managed local home entirely:

```bash
ontoskills uninstall --all
```
