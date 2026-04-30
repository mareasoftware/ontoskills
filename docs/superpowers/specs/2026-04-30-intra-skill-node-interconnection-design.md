---
title: Intra-Skill Node Interconnection Design
date: 2026-04-30
status: approved
---

# Intra-Skill Node Interconnection

**Goal:** Connect KnowledgeNodes to their source sections, AntiPatterns to correct alternatives, and constraints to the workflow steps they apply to — eliminating detached knowledge islands and enabling deduplication in the compact format.

**Why:** Today, KnowledgeNodes hang off the skill root with no structural link to sections. An AntiPattern says "don't do X" without pointing to the correct approach. A Constraint about "always validate" floats free instead of attaching to the workflow step where it matters. The compact format duplicates content that exists in both KN form and section form.

**Scope:** Compiler (URI generation + link inference), MCP server (enriched compact format), core ontology (3 new properties). No changes to SKILL.md authoring.

---

## 1. URI Scheme for All Nodes

Every node inside a skill receives a deterministic URI. Replace blank nodes with named resources.

**Pattern:** `oc:{prefix}_{hash}` where hash = `sha256(skill_hash:type:path)[:16]`

| Node Type | Prefix | Example |
|-----------|--------|---------|
| Section / Subsection | `sec` | `oc:sec_a3f2b01c` |
| Paragraph | `par` | `oc:par_c1e5f02d` |
| CodeExample | `code` | `oc:code_d7a3b18e` |
| BulletList | `list` | `oc:list_e9c2d43f` |
| Table | `tab` | `oc:tab_f4a1c56b` |
| KnowledgeNode | `kn` | `oc:kn_e3064b92` (already exists) |

**Path format:** `root:{section_order}:{section_title}:{content_order}:...` — same as current `make_bnode()` input.

**TTL before:**
```turtle
oc:skill_xxx oc:hasSection [ a oc:Section ; oc:sectionTitle "CRITICAL: Use Formulas" ; ... ] .
```

**TTL after:**
```turtle
oc:skill_xxx oc:hasSection oc:sec_a3f2b01c .
oc:sec_a3f2b01c a oc:Section ; oc:sectionTitle "CRITICAL: Use Formulas" ; ... .
```

**Invariants:**
- Same SKILL.md always produces same URIs (deterministic hash).
- KnowledgeNode URIs unchanged (already named).
- WorkflowStep already uses `_:ref_` pattern — promote to `oc:step_` with same hash.

---

## 2. OWL Properties

Three new object properties in `ontoskills/core.ttl`:

### `oc:derivedFromSection`
- **Domain:** `oc:KnowledgeNode`
- **Range:** `oc:Section`
- **Meaning:** This KN was inferred from this section's content.
- **Inverse:** `oc:isSourceOf` (Section → KnowledgeNode)
- **Always generated** when the compiler can identify the source section.

### `oc:correctAlternative`
- **Domain:** `oc:AntiPattern`
- **Range:** `oc:Section` or `oc:CodeExample`
- **Meaning:** The correct approach that should be used instead of this anti-pattern.
- **Inverse:** `oc:isAlternativeTo` (Section/CodeExample → AntiPattern)
- **Generated** when keyword matching finds a "correct"/"recommended" section in the same parent.

### `oc:appliesToStep`
- **Domain:** `oc:KnowledgeNode`
- **Range:** `oc:WorkflowStep`
- **Meaning:** This KN applies specifically to this workflow step.
- **Inverse:** `oc:hasConstraint` (WorkflowStep → KnowledgeNode)
- **Generated** when `appliesToContext` contains numeric step references matching a workflow.

---

## 3. Compiler Changes

### 3A. URI Promotion (`serialization.py`)

Replace `make_bnode()` with `make_uri()`:

```python
def make_uri(component_type: str, identifier: str) -> URIRef:
    prefixes = {
        "Section": "sec", "Subsection": "sec",
        "Paragraph": "par", "CodeExample": "code",
        "BulletList": "list", "Table": "tab",
        "WorkflowStep": "step",
    }
    prefix = prefixes.get(component_type, "node")
    raw = f"{skill.hash}:{component_type}:{identifier}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return URIRef(f"oc:{prefix}_{digest}")
```

The function `_serialize_section_tree` uses named nodes instead of blank nodes. All `BNode()` calls become `make_uri()` calls. The nesting structure (`oc:hasSection`, `oc:hasSubsection`, `oc:hasContent`) remains identical.

### 3B. Link Inference (new `linker.py`)

A post-processing pass that runs after all nodes are generated. Takes the RDF graph, analyzes it, and adds link triples.

**Strategy 1 — `derivedFromSection` (positional, always)**

The compiler already knows which section each KN came from because the LLM extraction step annotates KNs with source context. Map the source context to the section URI.

If the source context annotation is missing, fall back to structural position: find the section whose `oc:sectionTitle` has the highest token overlap with the KN's `oc:appliesToContext`.

**Strategy 2 — `correctAlternative` (keyword matching, conservative)**

For each AntiPattern KN with `derivedFromSection` pointing to section S:
1. Search sibling sections (same parent) for titles containing: "correct", "recommended", "instead", "proper", "best practice", or the negation of the anti-pattern's topic.
2. If found with high confidence (≥2 keyword match or title negation match), create `oc:correctAlternative`.
3. Also check CodeExample blocks within the same parent section — if one demonstrates the correct approach, link to it.

**Strategy 3 — `appliesToStep` (numeric reference)**

For each KN whose `appliesToContext` contains patterns like "step N", "Nth step", or matches a workflow step's `oc:stepLabel`:
1. Find the WorkflowStep with matching index or label.
2. If exactly one match, create `oc:appliesToStep`.

**Confidence policy:** If multiple candidates match for `correctAlternative` or `appliesToStep`, skip the link. Better no link than a wrong one.

### 3C. Impact on TTL size

Expected increase: ~15-20% (named nodes + link triples). For a 1000-line TTL, expect ~1200 lines. This is acceptable because:
- The MCP's compact format deduplicates based on links (net token reduction for agents).
- The TTL is read by the Rust server once at startup; larger file = slightly slower load, not per-query cost.

---

## 4. MCP Server Changes

### 4A. Enriched KnowledgeNodeInfo (`catalog.rs`)

The `KnowledgeNodeInfo` struct gains a `links` field:

```rust
struct KnowledgeNodeLink {
    property: String,       // "correctAlternative"
    target_title: String,   // "Use Formulas, Not Hardcoded Values"
    target_type: String,    // "Section" | "CodeExample" | "WorkflowStep"
}

struct KnowledgeNodeInfo {
    // ... existing fields ...
    links: Vec<KnowledgeNodeLink>,
}
```

The SPARQL query in `get_knowledge_nodes()` adds an OPTIONAL block:

```sparql
OPTIONAL {
  ?kn oc:derivedFromSection ?srcSec .
  ?srcSec oc:sectionTitle ?srcTitle .
}
OPTIONAL {
  ?kn oc:correctAlternative ?corr .
  ?corr oc:sectionTitle ?corrTitle .
  ?corr a ?corrType .
}
OPTIONAL {
  ?kn oc:appliesToStep ?step .
  ?step oc:stepLabel ?stepLabel .
}
```

### 4B. Compact format with links (`compact.rs`)

Each KN line in the compact format gains link annotations when present:

```
  ANTI PATTERN (When writing calculations) [CRITICAL]:
  Never hardcode calculated values
  Why: openpyxl won't recalculate them
  → Correct: "Use Formulas, Not Hardcoded Values"
  → Applies to: step 2 (Write Data)
```

Format rules:
- Max 2 links per KN (correctAlternative + appliesToStep).
- `derivedFromSection` is NOT shown in the compact format — it's used internally for BM25 ranking and deduplication.
- Links shown only when they exist. Zero overhead for KNs without links.

### 4C. Deduplication in compact format

When a KN has `derivedFromSection` pointing to section S, and the compact format already shows content from section S (via SectionContent), skip the duplicate. Show only the KN (higher semantic value) with a note that the section exists.

This is the primary token efficiency gain: instead of showing both the section paragraph AND the KN constraint, show only the KN with its link.

### 4D. BM25 ranking improvement

The existing BM25 engine ranks knowledge nodes by query relevance. With `derivedFromSection`, the ranking also considers:
- If the query matches a section title, boost KNs derived from that section.
- If the query matches a workflow step label, boost KNs that apply to that step.

This is a minor scoring adjustment in `NodeBm25Engine::score()`, not a new feature.

---

## 5. Files to Modify

| File | Change |
|------|--------|
| `ontoskills/core.ttl` | Add 3 OWL properties + 3 inverse properties |
| `core/src/serialization.py` | `make_bnode()` → `make_uri()`, section tree uses named nodes |
| `core/src/linker.py` | **New file.** Link inference pass (3 strategies) |
| `core/src/compiler.py` | Call linker after serialization |
| `mcp/src/catalog.rs` | Enriched SPARQL query, `KnowledgeNodeLink` struct |
| `mcp/src/compact.rs` | Link annotations in compact format, deduplication logic |

**No changes to:** SKILL.md authoring, `core/src/extraction.py`, `mcp/src/main.rs`, benchmark code.

---

## 6. Verification

1. Compile a skill → check TTL has named nodes (no blank nodes except for inline literals).
2. Compile a skill with AntiPattern → check `oc:correctAlternative` triple exists.
3. Query MCP with `ontoskill("xlsx")` → check compact format shows link annotations.
4. Query MCP with BM25 query matching a section title → check KNs from that section rank higher.
5. Compare token count of compact format before/after → expect ≤ same or fewer tokens (deduplication).
6. Run `python -m pytest benchmark/tests/ -q` → existing tests pass.
7. Run SkillsBench benchmark → MCP results should be equal or better than before.

---

## 7. Out of Scope

- Inter-skill linking (skills linking to other skills) — already handled by `dependsOnSkill`, `extends`.
- Section-level querying as a new MCP API — agents don't know section names a priori.
- `illustratedBy` (KN → CodeExample) — fragile matching, covered by deduplication.
- `relatedContent` (Section → Section) — sections are already ordered.
- Changes to the LLM extraction step — KN extraction stays the same, linker adds links post-hoc.
