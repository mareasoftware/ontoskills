# Ontology OWL Semantics Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use @superpowers:subagent-driven-development (recommended) or @superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix OWL semantic violations in OntoSkills ontology for enable AI agents to reason correctly.

**Architecture:** Add dedicated properties with intuitive naming (fileHash, scriptExecutor, stepDependsOn) instead of reusing generic properties with domain mismatches. Use standard dcterms:description for workflows.

**Tech Stack:** Python, RDFLib, OWL, Pydantic

---

## Task 1: Update Core Ontology Properties
> **Files:**
> Modify: `core/src/core_ontology.py`
> Test: `tests/test_core_ontology.py`

- [ ] **Step 1: Add file properties to core_ontology.py**

Add after the existing Phase 2 properties (around line 470):

```python
    # ========== Phase 2: File Properties ==========

    # oc:filePath - Relative path from skill directory
    g.add((oc.filePath, RDF.type, OWL.DatatypeProperty))
    g.add((oc.filePath, RDFS.label, Literal("file path")))
    g.add((oc.filePath, RDFS.comment, Literal(
        "Relative path from skill directory"
    )))
    g.add((oc.filePath, RDFS.domain, oc.ReferenceFile))
    g.add((oc.filePath, RDFS.domain, oc.ExecutableScript))
    g.add((oc.filePath, RDFS.range, XSD.xstring))

    # oc:fileHash - SHA-256 hash of file content
    g.add((oc.fileHash, RDF.type, OWL.DatatypeProperty))
    g.add((oc.fileHash, RDFS.label, Literal("file hash")))
    g.add((oc.fileHash, RDFS.comment, Literal(
        "SHA-256 hash of file content"
    )))
    g.add((oc.fileHash, RDFS.domain, oc.ReferenceFile))
    g.add((oc.fileHash, RDFS.domain, oc.ExecutableScript))
    g.add((oc.fileHash, RDFS.range, XSD.xstring))

    # oc:fileSize - File size in bytes
    g.add((oc.fileSize, RDF.type, OWL.DatatypeProperty))
    g.add((oc.fileSize, RDFS.label, Literal("file size")))
    g.add((oc.fileSize, RDFS.comment, Literal(
        "File size in bytes"
    )))
    g.add((oc.fileSize, RDFS.domain, oc.ReferenceFile))
    g.add((oc.fileSize, RDFS.domain, oc.ExecutableScript))
    g.add((oc.fileSize, RDFS.range, XSD.integer))

    # oc:fileMimeType - MIME type of the file
    g.add((oc.fileMimeType, RDF.type, OWL.DatatypeProperty))
    g.add((oc.fileMimeType, RDFS.label, Literal("file MIME type")))
    g.add((oc.fileMimeType, RDFS.comment, Literal(
        "MIME type of the file"
    )))
    g.add((oc.fileMimeType, RDFS.domain, oc.ReferenceFile))
    g.add((oc.fileMimeType, RDFS.domain, oc.ExecutableScript))
    g.add((oc.fileMimeType, RDFS.range, XSD.string))
```

- [ ] **Step 2: Add script properties to core_ontology.py**

Add after file properties:
```python
    # ========== Phase 2: Executable Script Properties ==========

    # oc:scriptExecutor - Executor for script (python, bash, node)
    g.add((oc.scriptExecutor, RDF.type, OWL.DatatypeProperty))
    g.add((oc.scriptExecutor, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptExecutor, RDFS.label, Literal("script executor")))
    g.add((oc.scriptExecutor, RDFS.comment, Literal(
        "Executor for the script (python, bash, node, etc.)"
    )))
    g.add((oc.scriptExecutor, RDFS.range, XSD.xstring))

    # oc:scriptIntent - Whether script should be executed or read-only
    g.add((oc.scriptIntent, RDF.type, OWL.DatatypeProperty))
    g.add((oc.scriptIntent, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptIntent, RDFS.label, Literal("script intent")))
    g.add((oc.scriptIntent, RDFS.comment, Literal(
        "Whether script should be executed or is read-only"
    )))
    g.add((oc.scriptIntent, RDFS.range, XSD.string))

    # oc:scriptCommand - Command template for executing the script
    g.add((oc.scriptCommand, RDF.type, OWL.DatatypeProperty))
    g.add((oc.scriptCommand, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptCommand, RDFS.label, Literal("script command")))
    g.add((oc.scriptCommand, RDFS.comment, Literal(
        "Command template for executing the script"
    )))
    g.add((oc.scriptCommand, RDFS.range, XSD.xstring))

    # oc:scriptOutput - Description of script output
    g.add((oc.scriptOutput, RDF.type, OWL.DatatypeProperty))
    g.add((oc.scriptOutput, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptOutput, RDFS.label, Literal("script output")))
    g.add((oc.scriptOutput, RDFS.comment, Literal(
        "Description of what the script produces"
    )))
    g.add((oc.scriptOutput, RDFS.range, XSD.xstring))

    # oc:scriptHasRequirement - Links script to its requirements
    g.add((oc.scriptHasRequirement, RDF.type, OWL.ObjectProperty))
    g.add((oc.scriptHasRequirement, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptHasRequirement, RDFS.range, oc.Requirement))
    g.add((oc.scriptHasRequirement, RDFS.label, Literal("script has requirement")))
    g.add((oc.scriptHasRequirement, RDFS.comment, Literal(
        "Links an executable script to its requirements"
    )))
```

- [ ] **Step 3: Add workflow step dependency property**

Add after workflow properties:
```python
    # ========== Phase 2: Workflow Step Dependencies ==========

    # oc:stepDependsOn - Dependency between workflow steps (ObjectProperty!)
    g.add((oc.stepDependsOn, RDF.type, OWL.ObjectProperty))
    g.add((oc.stepDependsOn, RDFS.domain, oc.WorkflowStep))
    g.add((oc.stepDependsOn, RDFS.range, oc.WorkflowStep))
    g.add((oc.stepDependsOn, RDFS.label, Literal("step depends on")))
    g.add((oc.stepDependsOn, RDFS.comment, Literal(
        "Indicates that one workflow step depends on another step"
    )))
```

- [ ] **Step 4: Remove old duplicate/incorrect properties**

Remove or update the properties that are now superseded:
- `oc:relativePath` → replaced by `oc:filePath`
- `oc:executionIntent` → replaced by `oc:scriptIntent`
- `oc:commandTemplate` → replaced by `oc:scriptCommand`
- `oc:producesOutput` → replaced by `oc:scriptOutput`

- [ ] **Step 5: Commit ontology changes**

```bash
git add core/src/core_ontology.py
git commit -m "feat(ontology): add dedicated Phase 2 file/script/workflow properties"
```

---

## Task 2: Update Serialization to Use New Properties
> **Files:**
> Modify: `core/src/serialization.py`
    Test: `tests/test_serialization.py`

- [ ] **Step 1: Update Reference File serialization**

In `serialize_skill()` function, around line 227-239, change:
```python
    # Reference Files (progressive disclosure)
    for ref in getattr(skill, 'reference_files', []):
        ref_node = make_bnode("ref", ref.relative_path)
        graph.add((skill_uri, oc.hasReferenceFile, ref_node))
        graph.add((ref_node, RDF.type, oc.ReferenceFile))
        graph.add((ref_node, oc.filePath, Literal(ref.relative_path)))  # Changed
        graph.add((ref_node, oc.purpose, Literal(ref.purpose)))

        # O(1) lookup using pre-indexed files
        if ref.relative_path in files_index:
            f = files_index[ref.relative_path]
            graph.add((ref_node, oc.fileHash, Literal(f.content_hash)))  # Changed
            graph.add((ref_node, oc.fileSize, Literal(f.file_size)))  # Keep
            graph.add((ref_node, oc.fileMimeType, Literal(f.mime_type)))  # Changed
```

- [ ] **Step 2: Update Executable Script serialization**

In `serialize_skill()` function, around line 241-269, change:
```python
    # Executable Scripts
    for script in getattr(skill, 'executable_scripts', []):
        script_node = make_bnode("script", script.relative_path)
        graph.add((skill_uri, oc.hasExecutableScript, script_node))
        graph.add((script_node, RDF.type, oc.ExecutableScript))
        graph.add((script_node, oc.filePath, Literal(script.relative_path)))  # Changed
        graph.add((script_node, oc.scriptExecutor, Literal(script.executor)))  # Changed
        graph.add((script_node, oc.scriptIntent, Literal(script.execution_intent)))  # Changed

        if script.command_template:
            graph.add((script_node, oc.scriptCommand, Literal(script.command_template)))  # Changed

        # Requirements as blank nodes
        for req in script.requirements:
            req_node = make_bnode("req", req)
            graph.add((script_node, oc.scriptHasRequirement, req_node))  # Changed
            graph.add((req_node, RDF.type, oc.Requirement))
            graph.add((req_node, oc.requirementType, Literal("Tool")))
            graph.add((req_node, oc.requirementValue, Literal(req)))
            graph.add((req_node, oc.isOptional, Literal(False)))

        if script.produces_output:
            graph.add((script_node, oc.scriptOutput, Literal(script.produces_output)))  # Changed

        # O(1) lookup using pre-indexed files
        if script.relative_path in files_index:
            f = files_index[script.relative_path]
            graph.add((script_node, oc.fileHash, Literal(f.content_hash)))  # Changed
```

- [ ] **Step 3: Update Workflow serialization to use dcterms:description and ObjectProperty dependencies**

In `serialize_skill()` function, around line 270-289, change:
```python
    # Workflows
    for wf in getattr(skill, 'workflows', []):
        wf_node = make_bnode("workflow", wf.workflow_id)
        graph.add((skill_uri, oc.hasWorkflow, wf_node))
        graph.add((wf_node, RDF.type, oc.Workflow))
        graph.add((wf_node, oc.workflowId, Literal(wf.workflow_id)))
        graph.add((wf_node, oc.workflowName, Literal(wf.name)))
        graph.add((wf_node, DCTERMS.description, Literal(wf.description)))  # Changed to DCTERMS

        # Build step node mapping for dependency resolution
        step_nodes = {}
        for step in wf.steps:
            step_node = make_bnode("step", f"{wf.workflow_id}_{step.step_id}")
            step_nodes[step.step_id] = step_node
            graph.add((wf_node, oc.hasStep, step_node))
            graph.add((step_node, RDF.type, oc.WorkflowStep))
            graph.add((step_node, oc.stepId, Literal(step.step_id)))
            graph.add((step_node, DCTERMS.description, Literal(step.description)))  # Changed to DCTERMS
            if step.expected_outcome:
                graph.add((step_node, oc.expectedOutcome, Literal(step.expected_outcome)))

        # Add step dependencies as ObjectProperty (second pass after all nodes created)
        for step in wf.steps:
            step_node = step_nodes[step.step_id]
            for dep_id in step.depends_on:
                if dep_id in step_nodes:
                    dep_node = step_nodes[dep_id]
                    graph.add((step_node, oc.stepDependsOn, dep_node))  # Changed to ObjectProperty
```

- [ ] **Step 4: Commit serialization changes**

```bash
git add core/src/serialization.py
git commit -m "feat(serialization): use dedicated Phase 2 properties"
```

---

## Task 3: Fix Reserved Words Validation
> **Files:**
> Modify: `core/src/schemas.py:223-236`
    Test: `tests/test_schemas.py`

- [ ] **Step 1: Update reserved words in Frontmatter.validate_name()**

Replace the reserved words check:
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

- [ ] **Step 2: Commit validation changes**

```bash
git add core/src/schemas.py
git commit -m "fix(schemas): use OntoSkills reserved words in validation"
```

---

## Task 4: Update Tests
> **Files:**
    Modify: `tests/test_serialization.py`
    Create: `tests/test_core_ontology_phase2.py`

- [ ] **Step 1: Add test for new file properties**

```python
def test_file_properties_defined():
    """Test that new file properties are defined with correct domains."""
    from rdflib import Graph
    from compiler.core_ontology import create_core_ontology
    from compiler.config import BASE_URI
    from rdflib.namespace import Namespace

    oc = Namespace(BASE_URI)

    g = Graph()
    create_core_ontology()  # Creates in temp or use mock

    # Check file properties exist
    assert (oc.filePath, None, g) is not None
    assert (oc.fileHash, None, g) is not None
    assert (oc.fileSize, None, g) is not None
    assert (oc.fileMimeType, None, g) is not None
```

- [ ] **Step 2: Add test for script properties**

```python
def test_script_properties_defined():
    """Test that script properties are defined with correct domains."""
    from rdflib import Graph
    from compiler.core_ontology import create_core_ontology
    from compiler.config import BASE_URI
    from rdflib.namespace import Namespace

    oc = Namespace(BASE_URI)

    g = Graph()
    create_core_ontology()

    # Check script properties exist
    assert (oc.scriptExecutor, None, g) is not None
    assert (oc.scriptIntent, None, g) is not None
    assert (oc.scriptCommand, None, g) is not None
    assert (oc.scriptOutput, None, g) is not None
    assert (oc.scriptHasRequirement, None, g) is not None
```

- [ ] **Step 3: Add test for step dependency property**

```python
def test_step_depends_on_is_object_property():
    """Test that oc:stepDependsOn is an ObjectProperty with correct domain/range."""
    from rdflib import Graph, OWL
    from compiler.core_ontology import create_core_ontology
    from compiler.config import BASE_URI
    from rdflib.namespace import Namespace

    oc = Namespace(BASE_URI)

    g = Graph()
    create_core_ontology()

    # Check stepDependsOn is ObjectProperty
    assert (oc.stepDependsOn, RDF.type, OWL.ObjectProperty) in g
```

- [ ] **Step 4: Add test for reserved words validation**

```python
def test_reserved_words_blocked_in_any_segment():
    """Test that reserved words are blocked anywhere in skill name."""
    import pytest
    from compiler.schemas import Frontmatter

    # Should pass
    Frontmatter(name="my-skill", description="Test")

    # Should fail - reserved in middle
    with pytest.raises(ValueError, match="Reserved word"):
        Frontmatter(name="my-marea-skill", description="Test")

    # Should fail - reserved at start
    with pytest.raises(ValueError, match="Reserved word"):
        Frontmatter(name="ontoskills-helper", description="Test")

    # Should fail - reserved at end
    with pytest.raises(ValueError, match="Reserved word"):
        Frontmatter(name="helper-core", description="Test")
```

- [ ] **Step 5: Run all tests**

```bash
python3 -m pytest tests/test_core_ontology_phase2.py tests/test_schemas.py -v
```

Expected: All tests pass

- [ ] **Step 6: Commit test changes**

```bash
git add tests/test_core_ontology_phase2.py
git commit -m "test: add tests for Phase 2 ontology properties"
```

---

## Task 5: Regenerate Core Ontology
> **Files:**
    Run: `ontocore compile` command

- [ ] **Step 1: Regenerate core ontology**

```bash
cd /Users/marcello/Developer/Marea/ontoclaw/core
python3 -c "from compiler.core_ontology import create_core_ontology; create_core_ontology()"
```

- [ ] **Step 2: Verify new properties in generated TTL**

```bash
grep -E "(oc:fileHash|oc:scriptExecutor|oc:stepDependsOn)" ../ontoskills/ontoskills-core.ttl
```

Expected: All three properties found

- [ ] **Step 3: Commit regenerated ontology**

```bash
git add ../ontoskills/ontoskills-core.ttl
git commit -m "chore: regenerate core ontology with Phase 2 properties"
```

---

## Task 6: Update CHANGELOG
> **Files:**
    Modify: `core/CHANGELOG.md`

- [ ] **Step 1: Add changelog entry**

Add to CHANGELOG.md:
```markdown
## [0.9.3] - 2026-03-26

### Changed

- **OWL Semantic Fixes** — Breaking changes to ontology properties:
  - `oc:contentHash` on files → `oc:fileHash` (domain: ReferenceFile, ExecutableScript)
  - `oc:executor` on scripts → `oc:scriptExecutor` (domain: ExecutableScript)
  - `oc:executionIntent` → `oc:scriptIntent`
  - `oc:commandTemplate` → `oc:scriptCommand`
  - `oc:producesOutput` → `oc:scriptOutput`
  - `oc:hasRequirement` on scripts → `oc:scriptHasRequirement`
  - `oc:description` on workflows → `dcterms:description`
  - `oc:dependsOn` on steps with Literal → `oc:stepDependsOn` (ObjectProperty)
  - `oc:relativePath` → `oc:filePath`
  - `oc:mimeType` → `oc:fileMimeType`

### Fixed

- **Reserved words validation** — Now blocks OntoSkills system words (ontoskills, marea, mareasw, core, system, index) anywhere in skill name segments
```

- [ ] **Step 2: Commit changelog**

```bash
git add core/CHANGELOG.md
git commit -m "docs: update CHANGELOG for v0.9.3 OWL semantic fixes"
```

---

## Task 7: Final Verification and Push
> **Files:**
    Run: All tests

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/marcello/Developer/Marea/ontoclaw/core
python3 -m pytest tests/ -v
```

Expected: All tests pass (except pre-existing 8 failures unrelated to this change)

- [ ] **Step 2: Push to PR branch**

```bash
git push origin feat/skill-compiler-v2-anthropic-support
```

---

## Summary

| Task | Description | Files Modified |
|------|-------------|----------------|
| 1 | Update Core Ontology Properties | `core_ontology.py` |
| 2 | Update Serialization | `serialization.py` |
| 3 | Fix Reserved Words | `schemas.py` |
| 4 | Add Tests | New test file |
| 5 | Regenerate Ontology | `ontoskills-core.ttl` |
| 6 | Update CHANGELOG | `CHANGELOG.md` |
| 7 | Final Verification | Tests + Push |
