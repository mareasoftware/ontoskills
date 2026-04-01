---
title: Troubleshooting
description: Common issues with installs, store access, compiler setup, and OntoMCP
sidebar:
  order: 16
---

## Installation issues

### `ontoskills install mcp` fails

Check:

- Node.js 18+ is available
- The release artifacts for the current version exist
- Your machine can download GitHub release assets
- No proxy or firewall is blocking `github.com` and `api.github.com`

**Error: "Failed to fetch release metadata"**

Network connectivity issue. Check your internet connection and try again. If behind a corporate proxy:

```bash
export HTTPS_PROXY=http://proxy.example.com:8080
ontoskills install mcp
```

**Error: "Release does not contain asset"**

The platform may not be supported. Check available platforms:

```bash
# Supported: darwin-arm64, darwin-x64, linux-arm64, linux-x64
uname -m && uname -s
```

### `ontoskills install core` fails

The compiler requires Python 3.10+:

```bash
python3 --version
```

If Python is installed but not found:

```bash
export PYTHON=/path/to/python3
ontoskills install core
```

---

## Store and package issues

### "Package not found"

- Check the package ID spelling
- Run `ontoskills search <query>` to discover available packages
- If using a third-party store, verify it's configured:

```bash
ontoskills store list
```

### Store skill does not appear in OntoMCP

Skills are enabled by default on install. If a skill is not visible:

1. Check if it was disabled:

```bash
ontoskills list-installed
```

2. Re-enable if needed:

```bash
ontoskills enable mareasw/greeting/hello
```

3. Rebuild the index:

```bash
ontoskills rebuild-index
```

4. Restart the MCP process

### "Skill still not visible after enable"

The MCP server caches the ontology index. Ensure:

1. Index was rebuilt: `ontoskills rebuild-index`
2. MCP server was restarted (close and reopen your AI client)
3. Check `~/.ontoskills/ontologies/system/index.enabled.ttl` exists

---

## Compiler issues

### Compiler commands fail

Install the compiler first:

```bash
ontoskills install core
```

Then initialize the ontology foundation:

```bash
ontoskills init-core
```

### "ANTHROPIC_API_KEY not set"

The compiler requires an Anthropic API key for LLM-based knowledge extraction:

```bash
export ANTHROPIC_API_KEY="your-key-here"
ontoskills compile my-skill
```

Add to your shell profile (`~/.bashrc`, `~/.zshrc`) to persist.

### "SHACL validation failed"

Your skill is missing required fields. Check:

- At least one `resolvesIntent` (in "When To Use" section)
- A clear one-line nature statement at the top
- Proper YAML frontmatter with `name` and `description`

Run with verbose output for details:

```bash
ontoskills compile my-skill -v
```

### "Nature not extracted"

Add a clear one-line summary at the beginning of your SKILL.md:

```markdown
# Skill Title

A brief description of what this skill does.

## What It Does
...
```

### "Missing resolvesIntent"

Ensure your skill has a "When To Use" or similar section:

```markdown
## When To Use

Use this skill when the user wants to extract text from PDF files.
```

---

## Import issues

### Imported source repo compiled, but the skill still is not visible

Imported skills are enabled by default. If not visible:

1. Rebuild the index:

```bash
ontoskills rebuild-index
```

2. Restart the MCP process

3. If still not visible and the skill was previously disabled, re-enable it:

```bash
ontoskills enable <qualified-id>
ontoskills rebuild-index
```

### "Source import failed"

Ensure:

1. Git is installed and accessible
2. The repository URL is correct and accessible
3. OntoCore is installed: `ontoskills install core`

### "No SKILL.md files found"

The import process looks for `SKILL.md` files in the repository. Ensure:

- Files are named exactly `SKILL.md` (case-sensitive)
- Files are in the repository root or subdirectories
- Files have valid YAML frontmatter

---

## MCP connection issues

### "MCP server not starting"

Check the binary exists and is executable:

```bash
ls -la ~/.ontoskills/bin/ontomcp
```

If missing, reinstall:

```bash
ontoskills install mcp
```

### "Connection refused" or "Timeout"

The MCP server may be slow to start. Check:

1. Server is running: `ps aux | grep ontomcp`
2. No port conflicts
3. Sufficient system resources

### "Claude Code cannot find ontomcp"

Ensure `~/.ontoskills/bin` is in your PATH, or use the full path in your MCP configuration:

```json
{
  "command": "/home/user/.ontoskills/bin/ontomcp"
}
```

---

## Index and state issues

### "Index corrupted"

Rebuild from scratch:

```bash
ontoskills rebuild-index
```

If that fails, check the lock file:

```bash
cat ~/.ontoskills/state/registry.lock.json
```

### "State files missing"

The state directory should contain:

- `registry.sources.json` — configured stores
- `registry.lock.json` — installed packages

If missing, they'll be recreated on next operation.

### "Permission denied" errors

Check ownership of `~/.ontoskills/`:

```bash
ls -la ~/.ontoskills/
```

Fix permissions if needed:

```bash
chmod -R u+rw ~/.ontoskills/
```

---

## Diagnostic tools

### `ontoskills doctor`

Run a comprehensive health check:

```bash
ontoskills doctor
```

This checks:

- MCP binary exists and is executable
- Core ontology is valid
- Environment variables are set
- Index is consistent
- Available updates

### Verbose output

Most commands support `-v` for detailed logging:

```bash
ontoskills compile my-skill -v
ontoskills install mcp -v
```

---

## Reset and recovery

### Reset everything

To remove the entire managed home:

```bash
ontoskills uninstall --all
```

**Warning:** This deletes everything under `~/.ontoskills/`.

### Reinstall from scratch

```bash
ontoskills uninstall --all
ontoskills install mcp
ontoskills install core  # if needed
ontoskills init-core     # if needed
# Re-install skills
ontoskills install mareasw/greeting/hello
```

---

## Getting help

If your issue isn't covered here:

1. Run `ontoskills doctor` and check the output
2. Search existing issues on GitHub
3. Open a new issue with:
   - `ontoskills doctor` output
   - Command that failed
   - Error message
   - Your OS and version
