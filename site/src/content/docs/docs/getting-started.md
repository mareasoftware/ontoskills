---
title: Getting Started
description: Install OntoSkills and query your first skill
sidebar:
  order: 2
---

In this tutorial, you'll install OntoSkills and run your first SPARQL query against a compiled skill ontology.

**What you'll have at the end:**
- A working OntoSkills installation
- A skill installed from OntoStore
- A successful SPARQL query result

Time: ~5 minutes

---

## Prerequisites

Before you start, make sure you have:

- **Node.js** 18+ ([install](https://nodejs.org/))
- **Git** ([install](https://git-scm.com/))
- **Anthropic API key** (get one at [console.anthropic.com](https://console.anthropic.com/))

---

## Step 1: Install the CLI

Open your terminal and run:

```bash
npx ontoskills install mcp
```

This creates a managed home at `~/.ontoskills/` with:
- `bin/ontomcp` — the MCP runtime
- `ontologies/` — compiled ontology packages
- `state/` — lockfiles and metadata

**Expected output:**
```
✓ Installed ontomcp to ~/.ontoskills/bin/ontomcp
✓ Created ~/.ontoskills/ontologies/
✓ Created ~/.ontoskills/state/
```

---

## Step 2: Install a skill from OntoStore

OntoStore is built in. Let's install a greeting skill:

```bash
ontoskills search hello
```

**Expected output:**
```
Found 1 skill:
  mareasw/greeting/hello - Simple greeting skill
```

Install it (auto-enabled on install):

```bash
ontoskills install mareasw/greeting/hello
```

**Expected output:**
```
✓ Installed mareasw/greeting/hello
```

---

## Step 3: Query the skill

Now let's query the installed skill using SPARQL:

```bash
ontoskills query "SELECT ?skill ?intent WHERE { ?skill a oc:Skill . ?skill oc:resolvesIntent ?intent }"
```

**Expected output:**
```text
?skill                    ?intent
─────────────────────────────────────
skill:hello               "say_hello"
```

You just queried a compiled ontology. The result is deterministic — same query, same result, every time.

---

## Step 4: (Optional) Install the compiler

If you want to write custom skills from source, install the compiler:

```bash
ontoskills install core
```

Requirements:
- **Python** 3.10+
- `ANTHROPIC_API_KEY` environment variable set

```bash
export ANTHROPIC_API_KEY="your-key-here"
ontoskills init-core
```

This creates `core.ttl` — the base ontology with classes and properties.

---

## Step 5: (Optional) Write your first skill

Create a simple skill:

```bash
mkdir -p skills/my-first-skill
```

Create `skills/my-first-skill/SKILL.md`:

```markdown
# My First Skill

A simple demonstration skill.

## What It Does

This skill greets the user by name.

## When To Use

Use when the user wants a friendly greeting.

## How To Use

1. Ask for the user's name
2. Say "Hello, {name}!"
```

Compile it:

```bash
ontoskills compile my-first-skill
```

**Expected output:**
```
✓ Compiled my-first-skill
  Nature: A simple demonstration skill
  Intents: greet_user
```

Query your skill:

```bash
ontoskills query "SELECT ?intent WHERE { skill:my_first_skill oc:resolvesIntent ?intent }"
```

---

## What you learned

- How to install OntoSkills CLI and MCP runtime
- How to install skills from OntoStore
- How to query skills with SPARQL
- (Optional) How to write and compile your own skill

---

## Next steps

Now that you're set up:

| Goal | Read |
|------|------|
| Learn all CLI commands | [CLI Reference](/cli/) |
| Browse available skills | [OntoStore](/ontostore/) |
| Write custom skills | [Skill Authoring](/authoring/) |
| Understand how it works | [Architecture](/architecture/) |
| Connect to your AI client | [MCP Setup](/mcp/) |
| Fix issues | [Troubleshooting](/troubleshooting/) |

---

## Common issues

### "Command not found: ontoskills"

Make sure you ran `npx ontoskills install mcp` and the `~/.ontoskills/bin` directory is in your PATH, or use `npx ontoskills` as the command.

### "ANTHROPIC_API_KEY not set"

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

Add this to your shell profile (`~/.bashrc`, `~/.zshrc`) to persist.

### "No skills found"

Skills are enabled by default on install. If you previously disabled one, re-enable it:

```bash
ontoskills enable mareasw/greeting/hello
```

### "SHACL validation failed"

Your skill is missing required fields. Check:
- At least one `resolvesIntent`
- The skill has clear structure

Run with `-v` for details:

```bash
ontoskills compile my-skill -v
```
