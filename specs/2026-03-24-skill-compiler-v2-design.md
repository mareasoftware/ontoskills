# Skill Compiler V2 — Design Document

**Date:** 2026-03-24
**Status:** Approved
**Author:** Claude + Marcello

---

## Executive Summary

This document specifies the redesign of the OntoSkills compiler to achieve **full compatibility** with Anthropic's skill authoring best practices. The new architecture introduces:

1. **Two-phase extraction** — Python preprocessing + LLM semantic extraction
2. **Progressive disclosure** — Hash-based lazy loading via RDF queries
3. **Complete feature coverage** — Frontmatter, reference files, scripts, examples, workflows

---

## 1. Architecture Overview

```
SKILL.md
    │
    ▼
┌─────────────────────────────────────┐
│  PHASE 1: Python (no LLM)           │
│  - Parse YAML frontmatter           │
│  - Validate name/description        │
│  - Scan directory structure         │
│  - Compute file hashes              │
│  - Build skill_id, qualified_id     │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  PHASE 2: LLM Extraction            │
│  - Receives: SKILL.md content       │
│              + directory structure  │
│              + pre-extracted metadata│
│  - Extracts: nature, genus, intents,│
│              knowledge_nodes,       │
│              workflows, examples    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  MERGE: Combines Phase 1 + Phase 2  │
│  - Final validation                 │
│  - Transform → OWL/Turtle           │
└─────────────────────────────────────┘
```

---

## 2. OWL Schema — New Classes

### 2.1 Class Hierarchy

```
oc:Skill
├── oc:DeclarativeSkill          # Skill with instructions only
└── oc:ExecutableSkill           # Skill with executable scripts

oc:SkillComponent                # Nested components
├── oc:ReferenceFile             # FORMS.md, REFERENCE.md, etc.
├── oc:ExecutableScript          # scripts/*.py, scripts/*.sh
├── oc:Template                  # Templates with placeholders
├── oc:Example                   # Input/output pairs
└── oc:Workflow                  # Sequential steps
    └── oc:WorkflowStep          # Single step with dependencies
```

### 2.2 Skill Properties

```turtle
oc:Skill
    oc:hasName              xsd:string    # From frontmatter, max 64 chars
    oc:hasDescription       xsd:string    # From frontmatter, max 1024 chars
    oc:hasFrontmatter       rdf:JSON      # Full YAML preserved
    oc:hasComponent         oc:SkillComponent
    oc:contentHash          xsd:string    # Directory hash
    oc:provenancePath       xsd:string    # Relative path
    oc:qualifiedId          xsd:string    # package/skill-id
    # ... existing properties (intents, knowledge_nodes, etc.)
```

### 2.3 ReferenceFile Properties

```turtle
oc:ReferenceFile
    oc:relativePath         xsd:string    # "reference/finance.md"
    oc:contentHash          xsd:string    # SHA-256 of file
    oc:fileSize             xsd:integer   # Bytes
    oc:mimeType             xsd:string    # "text/markdown"
    oc:purpose              xsd:string    # "api-reference" | "examples" | "guide" | "domain-specific" | "other"
```

### 2.4 ExecutableScript Properties

```turtle
oc:ExecutableScript
    oc:relativePath         xsd:string    # "scripts/analyze.py"
    oc:contentHash          xsd:string
    oc:executor             xsd:string    # "python" | "bash" | "node" | "other"
    oc:executionIntent      xsd:string    # "execute" | "read_only"
    oc:commandTemplate      xsd:string    # "python {script} {input}"
    oc:hasRequirement       oc:Requirement
    oc:producesOutput       xsd:string    # Expected output format
```

### 2.5 Workflow Properties

```turtle
oc:Workflow
    oc:workflowId           xsd:string
    oc:workflowName         xsd:string
    oc:description          xsd:string
    oc:hasStep              oc:WorkflowStep

oc:WorkflowStep
    oc:stepId               xsd:string
    oc:description          xsd:string
    oc:expectedOutcome      xsd:string
    oc:dependsOn            xsd:string    # Previous step IDs
```

---

## 3. Pydantic Models

### 3.1 Phase 1 Models (Python-only)

```python
class Frontmatter(BaseModel):
    """Extracted via Python YAML parser."""
    name: str                              # Validated: max 64, lowercase, hyphens
    description: str                       # Validated: max 1024, no XML tags
    version: str | None = None
    metadata: dict[str, Any] = {}

class FileInfo(BaseModel):
    """Computed via Python, not LLM."""
    relative_path: str
    content_hash: str
    file_size: int
    mime_type: str

class DirectoryScan(BaseModel):
    """Phase 1 output."""
    frontmatter: Frontmatter
    skill_id: str
    qualified_id: str
    content_hash: str
    provenance_path: str
    files: list[FileInfo]
    skill_md_content: str
```

### 3.2 Phase 2 Models (LLM Extraction)

```python
class ReferenceFile(BaseModel):
    relative_path: str
    purpose: Literal["api-reference", "examples", "guide", "domain-specific", "other"]

class ExecutableScript(BaseModel):
    relative_path: str
    executor: Literal["python", "bash", "node", "other"]
    execution_intent: Literal["execute", "read_only"] = "execute"
    command_template: str | None = None
    requirements: list[str] = []
    produces_output: str | None = None

class Example(BaseModel):
    name: str
    input_description: str
    output_example: str
    tags: list[str] = []

class WorkflowStep(BaseModel):
    step_id: str
    description: str
    expected_outcome: str | None = None
    depends_on: list[str] = []

class Workflow(BaseModel):
    workflow_id: str
    name: str
    description: str
    steps: list[WorkflowStep]

class LlmExtraction(BaseModel):
    """Phase 2 output."""
    nature: Literal["Tool", "Concept", "Work"]
    genus: str
    differentia: str
    intents: list[str]
    reference_files: list[ReferenceFile] = []
    executable_scripts: list[ExecutableScript] = []
    examples: list[Example] = []
    workflows: list[Workflow] = []
    knowledge_nodes: list[KnowledgeNode] = []
    depends_on: list[str] = []
    extends: list[str] = []
    contradicts: list[str] = []
    implements: list[str] = []
    exemplifies: list[str] = []
    state_transitions: StateTransition | None = None
    requirements: list[Requirement] = []
```

### 3.3 Merged Model

```python
class CompiledSkill(BaseModel):
    """Final compiler output."""
    # From Phase 1
    id: str
    qualified_id: str
    content_hash: str
    provenance_path: str
    frontmatter: Frontmatter
    files: list[FileInfo]

    # From Phase 2
    nature: str
    genus: str
    differentia: str
    intents: list[str]
    reference_files: list[ReferenceFile]
    executable_scripts: list[ExecutableScript]
    examples: list[Example]
    workflows: list[Workflow]
    knowledge_nodes: list[KnowledgeNode]
    depends_on: list[str]
    extends: list[str]
    contradicts: list[str]
    implements: list[str]
    exemplifies: list[str]
    state_transitions: StateTransition | None
    requirements: list[Requirement]
```

---

## 4. Progressive Disclosure

### 4.1 TTL with Blank Nodes

Components use blank nodes (no global URIs) since they have no identity outside their parent skill:

```turtle
oc:skill_copywriting a oc:DeclarativeSkill ;
    oc:hasName "copywriting" ;
    oc:hasDescription "When the user wants to write marketing copy..." ;
    oc:hasReferenceFile [
        a oc:ReferenceFile ;
        oc:relativePath "references/copy-frameworks.md" ;
        oc:contentHash "a3f2b8c9..." ;
        oc:fileSize 4521 ;
        oc:mimeType "text/markdown" ;
        oc:purpose "api-reference"
    ] , [
        a oc:ReferenceFile ;
        oc:relativePath "references/natural-transitions.md" ;
        oc:contentHash "d7e4f1a2..." ;
        oc:fileSize 1823 ;
        oc:mimeType "text/markdown" ;
        oc:purpose "guide"
    ] ;
    oc:hasExecutableScript [
        a oc:ExecutableScript ;
        oc:relativePath "scripts/analyze.py" ;
        oc:contentHash "b4c5d6e7..." ;
        oc:executor "python" ;
        oc:executionIntent "execute" ;
        oc:commandTemplate "python {script} {input} > {output}"
    ] .
```

### 4.2 SPARQL Queries for Lazy Loading

```sparql
# Get all reference files for a skill
PREFIX oc: <https://ontoskills.sh/ontology#>
SELECT ?path ?hash ?purpose ?size
WHERE {
    ?skill oc:hasName "copywriting" ;
           oc:hasReferenceFile ?ref .
    ?ref oc:relativePath ?path ;
         oc:contentHash ?hash ;
         oc:purpose ?purpose ;
         oc:fileSize ?size .
}
ORDER BY ?size

# Get executable scripts with execute intent
PREFIX oc: <https://ontoskills.sh/ontology#>
SELECT ?skillName ?path ?executor ?template
WHERE {
    ?skill oc:hasName ?skillName ;
           oc:hasExecutableScript ?script .
    ?script oc:executionIntent "execute" ;
            oc:relativePath ?path ;
            oc:executor ?executor ;
            oc:commandTemplate ?template .
}
```

### 4.3 MCP Server Validation Logic

```python
def load_reference_file(skill_path: Path, ref: FileMetadata) -> LoadResult:
    """Load reference file with hash verification."""
    full_path = skill_path / ref.relative_path

    if not full_path.exists():
        return LoadResult(status="missing", error=f"File not found: {ref.relative_path}")

    current_hash = compute_hash(full_path)

    if current_hash != ref.content_hash:
        return LoadResult(
            status="stale",
            warning=f"File changed. Expected {ref.content_hash[:8]}..., got {current_hash[:8]}...",
            content=full_path.read_text(),
            suggest_recompile=True
        )

    return LoadResult(status="valid", content=full_path.read_text(), metadata=ref)
```

---

## 5. Lint Rules

| Code | Severity | Description |
|------|----------|-------------|
| `missing-frontmatter` | ERROR | Skill without name/description |
| `invalid-skill-name` | ERROR | Name >64 chars or invalid format |
| `description-too-long` | WARNING | Description >1024 chars |
| `missing-intent` | ERROR | Skill without at least one intent |
| `orphan-reference` | WARNING | Reference file doesn't exist |
| `script-no-intent` | ERROR | Script without execution_intent |
| `invalid-script-path` | ERROR | Backslashes, path traversal, or absolute path |
| `workflow-cycle` | ERROR | Circular dependencies in workflow steps |
| `missing-step-dependency` | WARNING | Step depends on non-existent step |
| `dead-state` | WARNING | requires_state never yielded |
| `duplicate-intent` | ERROR | Intent declared by multiple skills |
| `circular-dep` | ERROR | Circular dependencies between skills |

### 5.1 Path Traversal Security Check

```python
def _check_script_validity(g: Graph, skill_dirs: dict[str, Path]) -> list[LintIssue]:
    issues = []

    for skill in g.subjects(RDF.type, OC.Skill):
        for script in g.objects(skill, OC.hasExecutableScript):
            path = next(g.objects(script, OC.relativePath), None)

            if path:
                path_str = str(path)

                # No backslashes
                if '\\' in path_str:
                    issues.append(LintIssue(
                        severity="error",
                        code="invalid-script-path",
                        skill_id=skill_id,
                        message="Script path uses backslashes",
                        location=path_str
                    ))

                # No path traversal
                if '..' in path_str.split('/'):
                    issues.append(LintIssue(
                        severity="error",
                        code="invalid-script-path",
                        skill_id=skill_id,
                        message="Script path contains directory traversal (..)",
                        location=path_str
                    ))

                # No absolute paths
                if path_str.startswith('/'):
                    issues.append(LintIssue(
                        severity="error",
                        code="invalid-script-path",
                        skill_id=skill_id,
                        message="Script path is absolute, must be relative",
                        location=path_str
                    ))

    return issues
```

---

## 6. Implementation Files

```
core/src/
├── loader.py              # NEW - Phase 1: frontmatter + directory scan
├── extractor.py           # MODIFY - Phase 2: LLM extraction
├── schemas.py             # MODIFY - new Pydantic models
├── transformer.py         # MODIFY - TTL generation with blank nodes
├── linter.py              # MODIFY - new validation checks
├── prompts.py             # MODIFY - new system prompt + tool schema
├── compiler.py            # NEW - 2-phase orchestration + merge
└── cli/
    └── compile.py         # MODIFY - uses new compiler
```

---

## 7. Token Budget

| Component | Estimated Tokens |
|-----------|------------------|
| System prompt | ~800 |
| Context (directory + SKILL.md) | ~1500-4000 |
| Tool schema | ~600 |
| LLM output | ~800-1500 |
| **Total per skill** | **~3700-6900** |

**Savings from Phase 1 preprocessing:** ~500-800 tokens per skill (frontmatter + file hashes not sent to LLM)

---

## 8. Breaking Changes

This is a **breaking change** from the existing compiler:

1. New OWL schema with additional classes and properties
2. Blank nodes for components instead of global URIs
3. Frontmatter extraction mandatory (skills without valid frontmatter will fail)
4. New lint rules may flag previously valid skills
5. All existing skills must be recompiled

---

## 9. Success Criteria

- [ ] All 6 sections implemented
- [ ] Existing skills recompile successfully
- [ ] Lint catches missing frontmatter
- [ ] Lint catches path traversal attempts
- [ ] MCP server can query reference files via SPARQL
- [ ] MCP server validates file hashes at runtime
- [ ] Token usage reduced by 500+ per skill vs v1
