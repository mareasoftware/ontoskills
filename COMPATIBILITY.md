# Version Compatibility

## Ontology Format

Current format version: `1.0`

Both OntoCore and OntoMCP must support the same ontology format version to work together.

## Tested Combinations

| OntoCore | OntoMCP | Ontology Format | Status   |
|----------|---------|-----------------|----------|
| 1.1.0    | 1.2.0   | 1.0             | Current  |
| 1.0.0    | 1.0.0   | 1.0             | Compatible |
| 0.11.0   | 0.11.0  | 0.11            | Compatible |
| 0.10.0   | 0.9.1   | 0.10            | Compatible |
| 0.9.1    | 0.9.1   | 0.9             | Compatible |
| 0.9.0    | 0.9.0   | 0.9             | Compatible |

> **Note:** OntoMCP 1.2.0 renames the MCP tool from `ontoskill` to `skill` and the server key from `ontoskills` to `onto`. Claude Code exposes it as `mcp__onto__skill`. Backward compat alias `ontoskill` is maintained for direct JSON-RPC callers. Ontology format 1.0 unchanged — no recompilation needed.

## Breaking Changes

When the ontology format changes, both packages must be updated together. Check this table before upgrading if you use both.

### 1.2.0
- **MCP tool renamed**: `ontoskill` → `skill`. Backward compat alias `ontoskill` maintained.
- **MCP server key**: `ontoskills` → `onto` in `.mcp.json`. Anyone using a custom `.mcp.json` must update.
- **Ontology format**: unchanged (still 1.0). No recompilation needed.
