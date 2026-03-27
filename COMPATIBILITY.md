# Version Compatibility

## Ontology Format

Current format version: `0.10`

Both OntoCore and OntoMCP must support the same ontology format version to work together.

## Tested Combinations

| OntoCore | OntoMCP | Ontology Format | Status   |
|----------|---------|-----------------|----------|
| 0.10.0   | 0.9.1   | 0.10            | Current  |
| 0.9.1    | 0.9.1   | 0.9             | Compatible |
| 0.9.0    | 0.9.0   | 0.9             | Compatible |

> **Note:** OntoMCP 0.9.1 supports ontology format 0.10 because the property changes in 0.10 (e.g., `oc:scriptExecutor` for `ExecutableScript`) do not affect the payload queries used by MCP (`oc:executor` on `ExecutionPayload`).

## Breaking Changes

When the ontology format changes, both packages must be updated together. Check this table before upgrading if you use both.
