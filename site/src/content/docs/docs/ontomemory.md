---
title: OntoMemory
description: Persistent runtime memory for graph-aware agents
sidebar:
  order: 7
---

`OntoMemory` stores remembered project and global knowledge as editable graph nodes. Memories are not sidecar notes: they are `oc:Memory` nodes, subclasses of `oc:KnowledgeNode`, and are loaded into the same OntoMCP runtime graph as compiled skills.

---

## What it stores

Each memory carries structured fields:

| Field | Purpose |
|-------|---------|
| `content` | The remembered directive, fact, procedure, correction, preference, or anti-pattern |
| `scope` | `project` or `global` write scope; search/list may use `both` |
| `memory_type` | `procedure`, `correction`, `anti_pattern`, `preference`, or `fact` |
| `related_skill_ids` | Skills the memory applies to |
| `related_intents` | Intent strings the memory applies to |
| `related_topic_ids` | Deterministic topic clusters |
| `related_memory_ids` | Thematically similar memories |
| `depends_on_memory_ids` | Supporting or prerequisite memories |
| `supersedes_memory_ids` | Older memories replaced by this memory |

Runtime memories are persisted as `.ttl` data and loaded with the rest of the ontology graph.

---

## Graph relations

OntoMemory uses explicit graph relationships instead of a flat note list.

| Relation | Meaning |
|----------|---------|
| `related_to_skill` | This memory is relevant to a compiled skill. |
| `related_to_intent` | This memory is relevant to an intent string. |
| `related_to_topic` | This memory belongs to a topic cluster. A memory can belong to multiple topics and act as a bridge between clusters. |
| `related_to_memory` | This memory is thematically similar to another memory, without implying sequence. |
| `depends_on_memory` | This memory depends on another memory; use it for operational chains. |
| `supersedes_memory` | This memory replaces, corrects, or versions an older memory. |

Primary RDF predicates include `oc:memoryId`, `oc:memoryScope`, `oc:directiveContent`, `oc:relatedToSkill`, `oc:relatedIntent`, `oc:relatedTopic`, `oc:relatedToMemory`, `oc:dependsOnMemory`, and `oc:supersedesMemory`.

---

## MCP actions

Use the `ontomemory` MCP tool:

```json
{
  "action": "remember",
  "content": "Release notes depend on the changelog and supersede older draft summaries.",
  "memory_type": "procedure",
  "related_intents": ["write_release_notes"],
  "depends_on_memory_ids": ["mem_changelog_source"],
  "supersedes_memory_ids": ["mem_old_release_summary"]
}
```

| Action | Purpose |
|--------|---------|
| `remember` | Save one or more memories. By default it decomposes compound thoughts, auto-associates graph links, merges duplicates, and avoids isolated nodes. |
| `associate` | Preview decomposition and graph associations without saving. |
| `search` / `list` | Retrieve memories by query, scope, skill, confidence, archive state, or limit. |
| `get` | Load one memory, optionally including dependency and superseded records. |
| `update` | Replace editable fields and relationship arrays. |
| `link` / `unlink` | Add or remove one explicit graph relation. |
| `forget` | Archive a memory or hard-delete it with `hard_delete=true`. |
| `recluster` | Recalculate topic clusters and generic memory links for existing memories. |

---

## Clustering and quality

Memory clustering v1 is deterministic and local. Embeddings are optional for skill discovery and are not required for OntoMemory clustering.

- `dedupe_policy=merge` merges similar memories by default; `reject` fails on duplicates; `allow` keeps them.
- `isolation_policy=auto_link` places memories in the graph by linking them to skills, intents, topics, or nearby memories; `reject` fails isolated memories; `inbox` assigns an unclassified topic.
- `auto_link_related=true` assigns topic clusters and links non-duplicate memories with related topic/context/intent signals.
- `recluster` backfills saved memories. Use `{"action":"recluster","dry_run":true}` to preview and `{"action":"recluster","apply":true}` to persist.

---

## OntoGraph

OntoGraph is the local 3D viewer/editor for the runtime graph. It shows skills, knowledge nodes, states, memories, intents, topics, and relationships.

Start it from the MCP binary:

```bash
cargo run --manifest-path mcp/Cargo.toml -- graph --ontology-root ./ontoskills
```

Or ask the MCP tool:

```json
{ "action": "start" }
```

The memory editor can create, edit, archive, hard-delete, and link memories. The graph view highlights memory chains, topic clusters, bridge memories, and incoming/outgoing relations for the selected node.
