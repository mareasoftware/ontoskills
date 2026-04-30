# Intra-Skill Node Interconnection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect KnowledgeNodes to their source sections, AntiPatterns to correct alternatives, and constraints to workflow steps — eliminating detached knowledge islands.

**Architecture:** Promote all blank nodes to named URIs in the compiler, add a post-serialization link inference pass, add 3 OWL properties to the ontology, and enrich the MCP compact format with link annotations.

**Tech Stack:** Python (rdflib, compiler), Rust (MCP/ontomcp), OWL/Turtle (ontology), SPARQL (queries)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `ontoskills/core.ttl` | OWL schema: 3 new object properties + 3 inverses |
| `core/src/serialization.py` | URI promotion: `make_bnode()` → `make_uri()` |
| `core/src/linker.py` | **New.** Post-serialization link inference (3 strategies) |
| `core/src/cli/compile.py` | Wire linker into pipeline after serialization |
| `mcp/src/catalog.rs` | Enriched `KnowledgeNodeInfo` with `links` field |
| `mcp/src/compact.rs` | Link annotations in compact format, deduplication |

---

### Task 1: Add OWL Properties to core.ttl

**Files:**
- Modify: `ontoskills/core.ttl:781` (after `oc:isExtendedBy`)

- [ ] **Step 1: Add 3 object properties and 3 inverse properties**

Insert after the `oc:isExtendedBy` block (after line 781), before `oc:BlockQuote` class (line 783):

```turtle
oc:derivedFromSection a owl:ObjectProperty ;
    rdfs:label "derived from section" ;
    rdfs:comment "Links a KnowledgeNode to the Section it was inferred from" ;
    rdfs:domain oc:KnowledgeNode ;
    rdfs:range oc:Section ;
    owl:inverseOf oc:isSourceOf .

oc:isSourceOf a owl:ObjectProperty ;
    rdfs:label "is source of" ;
    rdfs:comment "Links a Section to the KnowledgeNodes derived from it" ;
    rdfs:domain oc:Section ;
    rdfs:range oc:KnowledgeNode .

oc:correctAlternative a owl:ObjectProperty ;
    rdfs:label "correct alternative" ;
    rdfs:comment "Links an AntiPattern to the Section or CodeExample showing the correct approach" ;
    rdfs:domain oc:AntiPattern ;
    rdfs:range owl:Thing ;
    owl:inverseOf oc:isAlternativeTo .

oc:isAlternativeTo a owl:ObjectProperty ;
    rdfs:label "is alternative to" ;
    rdfs:comment "Links a Section/CodeExample to the AntiPattern it corrects" ;
    rdfs:domain owl:Thing ;
    rdfs:range oc:AntiPattern .

oc:appliesToStep a owl:ObjectProperty ;
    rdfs:label "applies to step" ;
    rdfs:comment "Links a KnowledgeNode to the WorkflowStep it applies to" ;
    rdfs:domain oc:KnowledgeNode ;
    rdfs:range oc:WorkflowStep ;
    owl:inverseOf oc:hasConstraint .

oc:hasConstraint a owl:ObjectProperty ;
    rdfs:label "has constraint" ;
    rdfs:comment "Links a WorkflowStep to KnowledgeNodes that constrain it" ;
    rdfs:domain oc:WorkflowStep ;
    rdfs:range oc:KnowledgeNode .
```

- [ ] **Step 2: Validate TTL syntax**

Run: `cd /home/marcello/Documenti/onto/ontoskills && python3 -c "from rdflib import Graph; g = Graph(); g.parse('ontoskills/core.ttl', format='turtle'); print(f'Triples: {len(g)}')"`

Expected: No parse errors, triple count ~200+.

- [ ] **Step 3: Commit**

```bash
git add ontoskills/core.ttl
git commit -m "feat(ontology): add intra-skill link properties (derivedFromSection, correctAlternative, appliesToStep)"
```

---

### Task 2: Promote Blank Nodes to Named URIs in serialization.py

**Files:**
- Modify: `core/src/serialization.py:392-402` (the `make_bnode` function)

- [ ] **Step 1: Replace `make_bnode()` with `make_uri()`**

In `core/src/serialization.py`, inside `serialize_skill()` (line 392), replace the `make_bnode` function:

```python
def make_uri(component_type: str, identifier: str) -> URIRef:
    """Create a deterministic URI from a fixed-length hash.

    Uses SHA-256 of {skill.hash}:{component_type}:{identifier} to ensure:
    - Fixed length (16 hex chars)
    - No collisions from identifier normalization
    - No TTL bloat from long identifiers
    """
    prefixes = {
        "section": "sec", "para": "par", "blist": "list",
        "bitem": "item", "bquote": "quote", "html": "html",
        "fm": "fm", "code": "code", "table": "tab",
        "flow": "flow", "tmpl": "tmpl", "proc": "wf",
        "step": "step", "workflow": "wf", "example": "ex",
        "ref": "ref",
    }
    prefix = prefixes.get(component_type, "node")
    raw = f"{skill.hash}:{component_type}:{identifier}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return URIRef(f"oc:{prefix}_{digest}")
```

Also rename the local variable `make_bnode` to `make_uri` everywhere it's used inside `serialize_skill()`. The function is passed to `_serialize_section_tree()` and called directly. All ~30 call sites remain the same — only the factory function changes from returning `BNode` to returning `URIRef`.

- [ ] **Step 2: Remove the `BNode` import if no longer needed**

Check if `BNode` is used anywhere else in the file. If `make_uri` is the only source of blank nodes and it now returns `URIRef`, the `BNode` import can be removed from line imports.

- [ ] **Step 3: Test by compiling one skill**

Run:
```bash
cd /home/marcello/Documenti/onto/ontoskills/core
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" PYTHONPATH=src .venv/bin/python -m compiler.cli compile \
  -i /tmp/skillsbench_full/tasks/earthquake-plate-calculation/environment/skills/geospatial-analysis/SKILL.md \
  -o /tmp/test_uri_promotion --skip-security -y -v
```

Then verify no blank nodes remain:
```bash
python3 -c "
from rdflib import Graph
g = Graph()
g.parse('/tmp/test_uri_promotion/geospatial-analysis/ontoskill.ttl', format='turtle')
# Count blank nodes (subjects starting with _:)
bnodes = [s for s in g.subjects() if str(s).startswith('_:')]
uris = [s for s in g.subjects() if not str(s).startswith('_:')]
print(f'Blank nodes: {len(bnodes)}')
print(f'URI nodes: {len(uris)}')
for b in bnodes[:5]:
    print(f'  BNode: {b}')
"
```

Expected: `Blank nodes: 0`, `URI nodes: 30+`.

- [ ] **Step 4: Run existing tests**

Run: `cd /home/marcello/Documenti/onto/ontoskills/core && python -m pytest tests/ -q`

Expected: All tests pass. If any tests reference `BNode` or blank node IDs, update them to expect `URIRef` with `oc:` prefix.

- [ ] **Step 5: Commit**

```bash
git add core/src/serialization.py core/tests/
git commit -m "feat(compiler): promote all blank nodes to named URIs in TTL output"
```

---

### Task 3: Create Linker Module

**Files:**
- Create: `core/src/linker.py`

- [ ] **Step 1: Write the linker module**

Create `core/src/linker.py`:

```python
"""Post-serialization link inference for intra-skill node interconnection.

Adds three types of links to the RDF graph after serialization:
1. derivedFromSection — KN → Section (positional)
2. correctAlternative — AntiPattern → Section/CodeExample (keyword)
3. appliesToStep — KN → WorkflowStep (numeric reference)
"""
import logging
import re
from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS

logger = logging.getLogger(__name__)

OC = "https://ontoskills.sh/ontology#"


def _oc(local: str) -> URIRef:
    return URIRef(f"{OC}{local}")


def _local(uri) -> str:
    """Extract local name from an oc: URI."""
    s = str(uri)
    return s.split("#")[-1] if "#" in s else s.split("/")[-1]


def infer_links(graph: Graph) -> int:
    """Run all link inference strategies on the graph. Returns count of links added."""
    total = 0
    total += _infer_derived_from_section(graph)
    total += _infer_correct_alternative(graph)
    total += _infer_applies_to_step(graph)
    logger.info("Link inference: added %d links", total)
    return total


def _infer_derived_from_section(graph: Graph) -> int:
    """Link each KnowledgeNode to the section whose title best matches its appliesToContext."""
    count = 0
    # Collect all sections with titles
    sections = {}
    for s in graph.subjects(RDF.type, _oc("Section")):
        titles = list(graph.objects(s, _oc("sectionTitle")))
        if titles:
            sections[s] = str(titles[0])

    if not sections:
        return 0

    # Collect all KnowledgeNodes (via impartsKnowledge)
    for skill in graph.subjects(_oc("impartsKnowledge), None):
        pass  # We iterate differently

    kns = set()
    for _, _, kn in graph.triples((None, _oc("impartsKnowledge"), None)):
        kns.add(kn)

    for kn in kns:
        # Skip if already linked
        if any(graph.triples((kn, _oc("derivedFromSection"), None))):
            continue

        # Get appliesToContext for matching
        contexts = list(graph.objects(kn, _oc("appliesToContext")))
        if not contexts:
            continue
        context_text = str(contexts[0]).lower()

        # Find best matching section by token overlap
        best_section = None
        best_score = 0
        context_tokens = set(re.findall(r'\w+', context_text))

        for sec, title in sections.items():
            title_tokens = set(re.findall(r'\w+', title.lower()))
            overlap = len(context_tokens & title_tokens)
            if overlap > best_score:
                best_score = overlap
                best_section = sec

        # Require at least 2 token overlap
        if best_section and best_score >= 2:
            graph.add((kn, _oc("derivedFromSection"), best_section))
            count += 1

    return count


def _infer_correct_alternative(graph: Graph) -> int:
    """For each AntiPattern, find a section/code in the same parent with correct approach."""
    count = 0

    # Correct approach keywords
    CORRECT_KEYWORDS = {"correct", "recommended", "proper", "instead", "best practice", "right way", "should"}

    # Collect AntiPatterns
    anti_patterns = set()
    for ap in graph.subjects(RDF.type, _oc("AntiPattern")):
        anti_patterns.add(ap)

    for ap in anti_patterns:
        if any(graph.triples((ap, _oc("correctAlternative"), None))):
            continue

        # Find which section this AP derives from
        derived_sections = list(graph.objects(ap, _oc("derivedFromSection")))
        if not derived_sections:
            continue

        parent_section = derived_sections[0]

        # Find the parent of that section (to search siblings)
        parents = list(graph.subjects(_oc("hasSection"), parent_section))
        parents += list(graph.subjects(_oc("hasSubsection"), parent_section))
        if not parents:
            continue
        parent = parents[0]

        # Collect sibling sections
        siblings = list(graph.objects(parent, _oc("hasSubsection")))
        siblings += list(graph.objects(parent, _oc("hasSection")))
        # Also check the skill root
        if _local(parent).startswith("skill_"):
            siblings += list(graph.objects(parent, _oc("hasSection")))

        for sibling in siblings:
            titles = list(graph.objects(sibling, _oc("sectionTitle")))
            if not titles:
                continue
            title_lower = str(titles[0]).lower()
            if any(kw in title_lower for kw in CORRECT_KEYWORDS):
                graph.add((ap, _oc("correctAlternative"), sibling))
                count += 1
                break

        # If no section found, try CodeExample in the same parent
        if not any(graph.triples((ap, _oc("correctAlternative"), None))):
            for content in graph.objects(parent_section, _oc("hasContent")):
                if any(graph.triples((content, RDF.type, _oc("CodeExample")))):
                    graph.add((ap, _oc("correctAlternative"), content))
                    count += 1
                    break

    return count


def _infer_applies_to_step(graph: Graph) -> int:
    """Link KnowledgeNodes to WorkflowSteps by numeric references in appliesToContext."""
    count = 0

    # Collect all workflow steps with their IDs and orders
    steps = {}
    for step in graph.subjects(RDF.type, _oc("WorkflowStep")):
        ids = list(graph.objects(step, _oc("stepId")))
        orders = list(graph.objects(step, _oc("stepOrder")))
        labels = list(graph.objects(step, _oc("stepLabel")))
        if ids:
            steps[step] = {
                "id": str(ids[0]),
                "order": int(orders[0]) if orders else -1,
                "label": str(labels[0]) if labels else "",
            }

    if not steps:
        return 0

    # Collect all KnowledgeNodes
    kns = set()
    for _, _, kn in graph.triples((None, _oc("impartsKnowledge"), None)):
        kns.add(kn)

    step_pattern = re.compile(r'(?:step\s+|#?\d+)\s*(\d+)', re.IGNORECASE)

    for kn in kns:
        if any(graph.triples((kn, _oc("appliesToStep"), None))):
            continue

        contexts = list(graph.objects(kn, _oc("appliesToContext")))
        if not contexts:
            continue
        context_text = str(contexts[0])

        # Try numeric reference
        match = step_pattern.search(context_text)
        if match:
            step_num = int(match.group(1))
            # Find matching step by order
            matching = [
                s for s, info in steps.items()
                if info["order"] == step_num
            ]
            if len(matching) == 1:
                graph.add((kn, _oc("appliesToStep"), matching[0]))
                count += 1
                continue

        # Try label match
        context_lower = context_text.lower()
        matching = [
            s for s, info in steps.items()
            if info["label"] and info["label"].lower() in context_lower
        ]
        if len(matching) == 1:
            graph.add((kn, _oc("appliesToStep"), matching[0]))
            count += 1

    return count
```

- [ ] **Step 2: Verify syntax**

Run: `cd /home/marcello/Documenti/onto/ontoskills/core && python3 -c "import sys; sys.path.insert(0, 'src'); from compiler.linker import infer_links; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/src/linker.py
git commit -m "feat(compiler): add linker module for intra-skill link inference"
```

---

### Task 4: Wire Linker into Compilation Pipeline

**Files:**
- Modify: `core/src/serialization.py:587-651` (the `serialize_skill_to_module` function)

- [ ] **Step 1: Add link inference call after serialization**

In `core/src/serialization.py`, inside `serialize_skill_to_module()`, after line 635 (`serialize_skill(g, skill, ...)`) and before line 642 (`validate_and_raise(g)`), add:

```python
    # Post-serialization: infer intra-skill links
    from compiler.linker import infer_links
    link_count = infer_links(g)
    if link_count:
        logger.debug("Inferred %d intra-skill links for %s", link_count, skill.skill_id)
```

This requires importing `logger` or using the module-level logger. Check what logger is available in the file — if none, add `import logging; logger = logging.getLogger(__name__)` at the top of the file.

- [ ] **Step 2: Test end-to-end compilation with links**

Run:
```bash
cd /home/marcello/Documenti/onto/ontoskills/core
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" PYTHONPATH=src .venv/bin/python -m compiler.cli compile \
  -i /tmp/skillsbench_full/tasks/exceltable-in-ppt/environment/skills/xlsx/SKILL.md \
  -o /tmp/test_linker --skip-security -y -v
```

Then verify links exist:
```bash
python3 -c "
from rdflib import Graph
g = Graph()
g.parse('/tmp/test_linker/xlsx/ontoskill.ttl', format='turtle')
oc = 'https://ontoskills.sh/ontology#'
derived = list(g.triples((None, URIRef(oc+'derivedFromSection'), None)))
correct = list(g.triples((None, URIRef(oc+'correctAlternative'), None)))
steps = list(g.triples((None, URIRef(oc+'appliesToStep'), None)))
print(f'derivedFromSection: {len(derived)}')
print(f'correctAlternative: {len(correct)}')
print(f'appliesToStep: {len(steps)}')
for s, p, o in derived[:3]:
    print(f'  {s} → {o}')
"
```

Expected: `derivedFromSection: 5+`, at least some `correctAlternative` and/or `appliesToStep`.

- [ ] **Step 3: Run all tests**

Run: `cd /home/marcello/Documenti/onto/ontoskills/core && python -m pytest tests/ -q`

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add core/src/serialization.py
git commit -m "feat(compiler): wire linker into serialization pipeline"
```

---

### Task 5: Enrich MCP Rust — KnowledgeNodeInfo with Links

**Files:**
- Modify: `mcp/src/catalog.rs:204-230` (KnowledgeNodeInfo struct)
- Modify: `mcp/src/catalog.rs:1012-1139` (get_knowledge_nodes SPARQL)

- [ ] **Step 1: Add `KnowledgeNodeLink` struct and `links` field**

In `mcp/src/catalog.rs`, add before `KnowledgeNodeInfo` (before line 204):

```rust
#[derive(Debug, Clone, Serialize)]
pub struct KnowledgeNodeLink {
    pub property: String,
    pub target_title: String,
    pub target_type: String,
}
```

Add to `KnowledgeNodeInfo` struct (after the `template_variables` field, around line 230):

```rust
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    pub links: Vec<KnowledgeNodeLink>,
```

Initialize `links: Vec::new()` in all places where `KnowledgeNodeInfo` is constructed.

- [ ] **Step 2: Enrich the SPARQL query with OPTIONAL link blocks**

In `get_knowledge_nodes()` (around line 1047), add to the SPARQL SELECT variables:

```
?srcSectionTitle ?correctTitle ?correctType ?stepLabel
```

Add OPTIONAL blocks before `ORDER BY`:

```sparql
OPTIONAL {
    ?node oc:derivedFromSection ?srcSec .
    ?srcSec oc:sectionTitle ?srcSectionTitle .
}
OPTIONAL {
    ?node oc:correctAlternative ?corr .
    ?corr a ?correctType .
    OPTIONAL { ?corr oc:sectionTitle ?correctTitle }
    FILTER(?correctType IN (oc:Section, oc:CodeExample))
}
OPTIONAL {
    ?node oc:appliesToStep ?linkedStep .
    ?linkedStep oc:stepLabel ?stepLabel .
}
```

- [ ] **Step 3: Parse link data from query results**

In the result parsing loop (around lines 1080-1136), extract link data:

```rust
let link_section_title = row.get("srcSectionTitle").and_then(|v| v.value()).map(|s| s.to_string());
let link_correct_title = row.get("correctTitle").and_then(|v| v.value()).map(|s| s.to_string());
let link_correct_type = row.get("correctType").and_then(|v| v.value()).map(|s| {
    let full = s.to_string();
    full.split('#').last().unwrap_or(&full).to_string()
});
let link_step_label = row.get("stepLabel").and_then(|v| v.value()).map(|s| s.to_string());
```

After constructing the `KnowledgeNodeInfo`, add links:

```rust
let mut links = Vec::new();
if let Some(title) = link_correct_title {
    links.push(KnowledgeNodeLink {
        property: "correctAlternative".into(),
        target_title: title,
        target_type: link_correct_type.unwrap_or_else(|| "Section".into()),
    });
}
if let Some(label) = link_step_label {
    links.push(KnowledgeNodeLink {
        property: "appliesToStep".into(),
        target_title: label,
        target_type: "WorkflowStep".into(),
    });
}
info.links = links;
```

- [ ] **Step 4: Build and verify compilation**

Run: `cd /home/marcello/Documenti/onto/ontoskills/mcp && cargo build 2>&1 | tail -20`

Expected: No errors. Warnings are acceptable.

- [ ] **Step 5: Commit**

```bash
git add mcp/src/catalog.rs
git commit -m "feat(mcp): enrich KnowledgeNodeInfo with link annotations from ontology"
```

---

### Task 6: Enrich Compact Format with Links and Deduplication

**Files:**
- Modify: `mcp/src/compact.rs:149-183` (KN formatting loop)

- [ ] **Step 1: Add link annotations after each KN's rationale line**

In `compact_context_with_query()`, inside the per-node formatting block (around line 170, after the `Why:` line), add:

```rust
for link in &node.links {
    match link.property.as_str() {
        "correctAlternative" => {
            out.push_str(&format!("  → Correct: \"{}\" ({})\n", link.target_title, link.target_type));
        }
        "appliesToStep" => {
            out.push_str(&format!("  → Applies to: {}\n", link.target_title));
        }
        _ => {}
    }
}
```

- [ ] **Step 2: Add section-title-based BM25 boost for derivedFromSection**

In `mcp/src/bm25_engine.rs`, inside `NodeBm25Engine::rank_nodes()` (around line 172), after scoring each node, check if any ranked section title matches a node's `derivedFromSection` link. This is optional — if the engine doesn't have access to section titles at ranking time, skip this and the BM25 boost will be handled in a follow-up.

For now, the link annotations in the compact format already provide value without BM25 changes.

- [ ] **Step 3: Build and test**

Run: `cd /home/marcello/Documenti/onto/ontoskills/mcp && cargo build 2>&1 | tail -10`

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add mcp/src/compact.rs
git commit -m "feat(mcp): add link annotations to compact format output"
```

---

### Task 7: End-to-End Integration Test

**Files:**
- Create: `core/tests/test_linker.py`

- [ ] **Step 1: Write integration test**

Create `core/tests/test_linker.py`:

```python
"""Integration test: compile a skill, verify intra-skill links are generated."""
import pytest
from rdflib import Graph, URIRef
from compiler.linker import infer_links

OC = "https://ontoskills.sh/ontology#"


def test_derived_from_section():
    """KnowledgeNodes should link to their source sections."""
    g = Graph()
    g.parse("ontoskills/core.ttl", format="turtle")

    # Build a minimal skill graph with one section and one KN
    skill = URIRef(f"{OC}skill_test")
    section = URIRef(f"{OC}sec_abc123")
    kn = URIRef(f"{OC}kn_def456")

    g.add((skill, URIRef(f"{OC}impartsKnowledge"), kn))
    g.add((kn, URIRef(f"{OC}appliesToContext"), Literal("When writing formulas to Excel cells")))
    g.add((kn, URIRef(f"{OC}directiveContent"), Literal("Never hardcode values")))
    g.add((kn, RDF.type, URIRef(f"{OC}AntiPattern")))

    g.add((skill, URIRef(f"{OC}hasSection"), section))
    g.add((section, RDF.type, URIRef(f"{OC}Section")))
    g.add((section, URIRef(f"{OC}sectionTitle"), Literal("Writing Formulas to Excel")))

    count = infer_links(g)
    assert count >= 1

    derived = list(g.triples((kn, URIRef(f"{OC}derivedFromSection"), None)))
    assert len(derived) == 1
    assert derived[0][2] == section


def test_correct_alternative():
    """AntiPatterns should link to sections with correct approach keywords."""
    from rdflib import Literal
    from rdflib.namespace import RDF

    g = Graph()
    g.parse("ontoskills/core.ttl", format="turtle")

    skill = URIRef(f"{OC}skill_test")
    ap_section = URIRef(f"{OC}sec_111")
    correct_section = URIRef(f"{OC}sec_222")
    kn = URIRef(f"{OC}kn_ap1")

    g.add((skill, URIRef(f"{OC}impartsKnowledge"), kn))
    g.add((kn, URIRef(f"{OC}appliesToContext"), Literal("When writing data to cells")))
    g.add((kn, URIRef(f"{OC}directiveContent"), Literal("Never hardcode")))
    g.add((kn, RDF.type, URIRef(f"{OC}AntiPattern")))

    g.add((skill, URIRef(f"{OC}hasSection"), ap_section))
    g.add((ap_section, RDF.type, URIRef(f"{OC}Section")))
    g.add((ap_section, URIRef(f"{OC}sectionTitle"), Literal("Writing data to cells")))

    g.add((skill, URIRef(f"{OC}hasSection"), correct_section))
    g.add((correct_section, RDF.type, URIRef(f"{OC}Section")))
    g.add((correct_section, URIRef(f"{OC}sectionTitle"), Literal("Correct way to write formulas")))

    # First run derivedFromSection, then correctAlternative
    infer_links(g)

    correct = list(g.triples((kn, URIRef(f"{OC}correctAlternative"), None)))
    assert len(correct) >= 1
```

- [ ] **Step 2: Run the test**

Run: `cd /home/marcello/Documenti/onto/ontoskills/core && python -m pytest tests/test_linker.py -v`

Expected: Both tests PASS.

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_linker.py
git commit -m "test(compiler): integration tests for intra-skill link inference"
```

---

## Verification Checklist

After all tasks are complete:

1. [ ] Compile a real skill → TTL has named nodes (no `_:ref_` blank nodes for sections/content)
2. [ ] Compiled TTL has `oc:derivedFromSection` triples linking KNs to sections
3. [ ] Compiled TTL has `oc:correctAlternative` triples for at least some AntiPatterns
4. [ ] MCP server starts and loads the new TTL without errors
5. [ ] `ontoskill("xlsx")` returns compact format with `→ Correct:` link annotations
6. [ ] `python -m pytest core/tests/ -q` — all tests pass
7. [ ] `cd mcp && cargo build` — no errors
8. [ ] Benchmark `python -m pytest benchmark/tests/ -q` — existing tests pass
