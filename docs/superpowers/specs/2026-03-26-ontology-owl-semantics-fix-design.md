# Ontology OWL Semantics Fix Design

**Date:** 2026-03-26
**Status:** Approved
**Scope:** Fix OWL semantic issues in OntoSkills ontology for AI agent compatibility

## Problem Statement

The OntoSkills ontology has several OWL semantic violations where properties are used on classes outside their declared domains. This causes:

1. **Incorrect OWL inferences** - Reasoners may infer that `ReferenceFile` is a `Skill`
2. **Ambiguous semantics for AI agents** - LLMs struggle with properties that have multiple meanings
3. **Invalid SPARQL queries** - Queries filtering by domain return unexpected results
4. **Literal instead of Object references** - Workflow step dependencies use strings instead of node references

## Design Goals

1. **Rigorous OWL correctness** - Ontology must be valid for OWL reasoners
2. **Future-proof for AI agents** - Clear, unambiguous semantics for LLM-based ontological agents
3. **Intuitive naming** - Property names that self-document their purpose
4. **Breaking change acceptable** - Few skills in store, clean migration path

## Solution: Dedicated Properties with Intuitive Naming

### Principle
Each property has ONE clear meaning in ONE context. This reduces cognitive load for AI agents and enables precise SPARQL queries.

---

## Section 1: File Properties

**Classes affected:** `oc:ReferenceFile`, `oc:ExecutableScript`

**New properties:**

```turtle
oc:filePath a owl:DatatypeProperty ;
    rdfs:label "file path" ;
    rdfs:comment "Relative path from skill directory" ;
    rdfs:domain [ owl:unionOf (oc:ReferenceFile oc:ExecutableScript) ] ;
    rdfs:range xsd:string .

oc:fileHash a owl:DatatypeProperty ;
    rdfs:label "file hash" ;
    rdfs:comment "SHA-256 hash of file content" ;
    rdfs:domain [ owl:unionOf (oc:ReferenceFile oc:ExecutableScript) ] ;
    rdfs:range xsd:string .

oc:fileSize a owl:DatatypeProperty ;
    rdfs:label "file size" ;
    rdfs:comment "File size in bytes" ;
    rdfs:domain [ owl:unionOf (oc:ReferenceFile oc:ExecutableScript) ] ;
    rdfs:range xsd:integer .

oc:fileMimeType a owl:DatatypeProperty ;
    rdfs:label "file MIME type" ;
    rdfs:comment "MIME type of the file" ;
    rdfs:domain [ owl:unionOf (oc:ReferenceFile oc:ExecutableScript) ] ;
    rdfs:range xsd:string .
```

**Rationale:** `fileHash` vs `contentHash` clearly distinguishes file-level hashes from skill-level hashes.

---

## Section 2: ExecutableScript Properties

**Class affected:** `oc:ExecutableScript`

**New properties:**

```turtle
oc:scriptExecutor a owl:DatatypeProperty ;
    rdfs:label "script executor" ;
    rdfs:comment "Executor for the script (python, bash, node, etc.)" ;
    rdfs:domain oc:ExecutableScript ;
    rdfs:range xsd:string .

oc:scriptIntent a owl:DatatypeProperty ;
    rdfs:label "script intent" ;
    rdfs:comment "Whether script should be executed or is read-only" ;
    rdfs:domain oc:ExecutableScript ;
    rdfs:range xsd:string .

oc:scriptCommand a owl:DatatypeProperty ;
    rdfs:label "script command" ;
    rdfs:comment "Command template for executing the script" ;
    rdfs:domain oc:ExecutableScript ;
    rdfs:range xsd:string .

oc:scriptOutput a owl:DatatypeProperty ;
    rdfs:label "script output" ;
    rdfs:comment "Description of what the script produces" ;
    rdfs:domain oc:ExecutableScript ;
    rdfs:range xsd:string .

oc:scriptHasRequirement a owl:ObjectProperty ;
    rdfs:label "script has requirement" ;
    rdfs:comment "Links an executable script to its requirements" ;
    rdfs:domain oc:ExecutableScript ;
    rdfs:range oc:Requirement .
```

**Naming convention:** `script*` prefix creates clear semantic boundary for AI agents.

---

## Section 3: Workflow and WorkflowStep Properties

### 3a. Description Property

**Solution:** Use standard `dcterms:description` for Workflow and WorkflowStep descriptions.

```turtle
# Reuse existing dcterms:description - no new property needed
# Just ensure serialization uses DCTERMS.description
```

### 3b. Step Dependencies (Critical Fix)

**Problem:** Current code uses `oc:dependsOn` with Literal values (step IDs as strings).

**Solution:** New ObjectProperty that references actual WorkflowStep nodes.

```turtle
oc:stepDependsOn a owl:ObjectProperty ;
    rdfs:label "step depends on" ;
    rdfs:comment "Indicates that one workflow step depends on another step" ;
    rdfs:domain oc:WorkflowStep ;
    rdfs:range oc:WorkflowStep .
```

**Implementation note:** When serializing, create a mapping `step_id → BNode` first, then use the BNode reference:

```python
# First pass: create all step nodes
step_nodes = {}
for step in wf.steps:
    step_nodes[step.step_id] = make_bnode("step", f"{wf.workflow_id}_{step.step_id}")

# Second pass: add dependencies using node references
for step in wf.steps:
    step_node = step_nodes[step.step_id]
    for dep_id in step.depends_on:
        if dep_id in step_nodes:
            graph.add((step_node, oc.stepDependsOn, step_nodes[dep_id]))
```

---

## Section 4: Example and Frontmatter Properties

### 4a. Example Properties (Already Correct)

```turtle
oc:exampleName a owl:DatatypeProperty ;
    rdfs:domain oc:Example ;
    rdfs:range xsd:string .

oc:exampleInput a owl:DatatypeProperty ;
    rdfs:domain oc:Example ;
    rdfs:range xsd:string .

oc:exampleOutput a owl:DatatypeProperty ;
    rdfs:domain oc:Example ;
    rdfs:range xsd:string .

oc:exampleTag a owl:DatatypeProperty ;
    rdfs:domain oc:Example ;
    rdfs:range xsd:string .
```

### 4b. Frontmatter Properties (Already Correct)

```turtle
oc:hasName a owl:DatatypeProperty ;
    rdfs:domain oc:Skill ;
    rdfs:range xsd:string .

oc:hasDescription a owl:DatatypeProperty ;
    rdfs:domain oc:Skill ;
    rdfs:range xsd:string .
```

---

## Section 5: Reserved Words Validation

**File:** `core/src/schemas.py`

**Current problem:** `my-marea-skill` passes because reserved words only checked as prefix/suffix.

**Solution:** Block reserved words in any hyphen-delimited segment:

```python
@field_validator('name')
@classmethod
def validate_name(cls, v: str) -> str:
    if len(v) > 64:
        raise ValueError(f"Skill name exceeds 64 characters: {len(v)}")
    if not re.match(r'^[a-z0-9-]+$', v):
        raise ValueError("Skill name must be lowercase with hyphens only")

    # Check for OntoSkills reserved words anywhere in the skill name
    reserved = ('ontoskills', 'marea', 'mareasw', 'core', 'system', 'index')
    segments = v.lower().split('-')
    for word in reserved:
        if word in segments:
            raise ValueError(f"Reserved word '{word}' not allowed in skill name")

    return v
```

---

## Migration Summary

| Old Property | New Property | Notes |
|--------------|--------------|-------|
| `oc:relativePath` | `oc:filePath` | Domain: ReferenceFile, ExecutableScript |
| `oc:contentHash` (on files) | `oc:fileHash` | Domain: ReferenceFile, ExecutableScript |
| `oc:fileSize` | `oc:fileSize` | Add unionOf domain |
| `oc:mimeType` | `oc:fileMimeType` | Domain: ReferenceFile, ExecutableScript |
| `oc:executor` (on script) | `oc:scriptExecutor` | Domain: ExecutableScript only |
| `oc:executionIntent` | `oc:scriptIntent` | Domain: ExecutableScript |
| `oc:commandTemplate` | `oc:scriptCommand` | Domain: ExecutableScript |
| `oc:producesOutput` | `oc:scriptOutput` | Domain: ExecutableScript |
| `oc:hasRequirement` (on script) | `oc:scriptHasRequirement` | Domain: ExecutableScript |
| `oc:description` | `dcterms:description` | Standard property |
| `oc:dependsOn` + Literal | `oc:stepDependsOn` + BNode | ObjectProperty |
| `oc:purpose` | `oc:purpose` | Keep, domain: ReferenceFile |

## Files to Modify

1. **`core/src/core_ontology.py`** - Add new properties, update domains
2. **`core/src/serialization.py`** - Use new property names
3. **`core/src/schemas.py`** - Fix reserved words validation
4. **Regenerate** `ontoskills/ontoskills-core.ttl` via `ontocore compile`
5. **Recompile** existing skills (breaking change)

## Success Criteria

- [ ] All new properties defined in `core_ontology.py` with correct domains
- [ ] `serialization.py` uses new property names
- [ ] Reserved words validation blocks words in any segment
- [ ] All tests pass
- [ ] Generated `.ttl` files validate with SHACL
- [ ] OWL reasoner (if available) makes no incorrect inferences
