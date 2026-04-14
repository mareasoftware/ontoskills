# Version Compatibility

## Ontology Format

Current format version: `0.11`

Both OntoCore and OntoMCP must support the same ontology format version to work together.

## Tested Combinations

| OntoCore | OntoMCP | Ontology Format | Status   |
|----------|---------|-----------------|----------|
| 0.11.0   | 0.9.1   | 0.11            | Current  |
| 0.10.0   | 0.9.1   | 0.10            | Compatible |
| 0.9.1    | 0.9.1   | 0.9             | Compatible |
| 0.9.0    | 0.9.0   | 0.9             | Compatible |

> **Note:** OntoMCP 0.9.1 supports ontology format 0.11 because all new properties (`oc:dependsOnSkill`, 9 optional metadata fields, per-skill embeddings) are additive and do not affect existing MCP queries. Trust-tier hybrid scoring uses data already loaded from `registry.lock.json`.

## Breaking Changes

When the ontology format changes, both packages must be updated together. Check this table before upgrading if you use both.
