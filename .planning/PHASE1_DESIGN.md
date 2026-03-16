# Phase 1: OntoClaw ETL Refactoring Design

## Overview

Transform the Python ETL from monolithic output to modular neuro-symbolic ontology with state-transition logic.

## 1. Namespace Configuration

**Base URI**: Environment-driven for enterprise deployment

```python
import os
BASE_URI = os.environ.get("ONTOCLAW_BASE_URI", "http://ontoclaw.marea.software/ontology#")
```

**Prefix**: `oc:` → `{BASE_URI}`

## 2. Directory Structure

```
ontoclaw/                          # Monorepo root
├── compiler/                      # Python ETL (this refactor)
│   ├── src/ontoclaw_compiler/
│   │   ├── schemas.py
│   │   ├── transformer.py
│   │   ├── loader.py
│   │   └── ...
├── skills/                        # Raw markdown input
│   └── office/public/docx/SKILL.md
└── semantic-skills/               # Compiled output
    ├── ontoclaw-core.ttl          # TBox (base classes, properties, core states)
    ├── index.ttl                  # Manifest with owl:imports
    └── office/public/docx/skill.ttl  # Mirrored structure
```

**Mirroring Rule**: `skills/{path}/SKILL.md` → `semantic-skills/{path}/skill.ttl`

## 3. Core TBox (ontoclaw-core.ttl)

Generated once at the root of `semantic-skills/`. Contains:

### Classes
- `oc:Skill` - Base class for all skills
- `oc:State` - Abstract state class (pre-conditions, outcomes, failures)
- `oc:Attempt` - Execution attempt record (for negative memory)

### Predefined Core States (Hybrid Taxonomy)
```
oc:SystemAuthenticated   - System credentials validated
oc:NetworkAvailable      - Network connectivity confirmed
oc:FileExists           - Required file present
oc:DirectoryWritable    - Target directory is writable
oc:APIKeySet            - Required API key configured
oc:ToolInstalled        - Required tool/cli available
oc:EnvironmentReady     - Runtime environment prepared
```

### Properties
```
oc:requiresState   (Skill → State)     - Pre-conditions
oc:yieldsState     (Skill → State)     - Success outcomes
oc:handlesFailure  (Skill → State)     - Failure states
oc:hasStatus       (Attempt → Status)  - Execution status (Success/Failed)
oc:generatedBy     (Skill → Literal)   - LLM attestation
```

## 4. Schema Changes (schemas.py)

### Remove
- `constraints: list[str]` - No backward compatibility

### Add
```python
class StateTransition(BaseModel):
    requires_state: list[str] = []   # URIs: ["oc:SystemAuthenticated"]
    yields_state: list[str] = []     # URIs: ["oc:DocumentCreated"]
    handles_failure: list[str] = []  # URIs: ["oc:PermissionDenied"]

class ExtractedSkill(BaseModel):
    # ... existing fields ...
    state_transitions: StateTransition = StateTransition()
    generated_by: str = "unknown"  # From ANTHROPIC_MODEL env var
```

## 5. Modular Output Format

### Individual Skill TTL (`skill.ttl`)
```turtle
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix prov: <http://www.w3.org/ns/prov#> .

<> a owl:Ontology ;
    owl:imports <http://ontoclaw.marea.software/ontology/core> .

oc:docx_engineering a oc:Skill ;
    dcterms:identifier "docx-engineering" ;
    oc:requiresState oc:ToolInstalled ;
    oc:yieldsState oc:DocumentCreated ;
    oc:handlesFailure oc:PermissionDenied ;
    prov:wasGeneratedBy "claude-sonnet-4-6" .
```

### Index Manifest (`index.ttl`)
```turtle
@prefix owl: <http://www.w3.org/2002/07/owl#> .

<> a owl:Ontology ;
    owl:imports <./ontoclaw-core.ttl> ,
                <./office/public/docx/skill.ttl> ,
                <./office/public/pdf/skill.ttl> .
```

## 6. LLM Extraction Prompt Updates

Add to system prompt in `transformer.py`:

```
## STATE TRANSITION EXTRACTION

Extract the skill's logic as a state machine:

1. **requiresState**: What must be true BEFORE this skill can run?
   - Prefer predefined URIs: oc:SystemAuthenticated, oc:NetworkAvailable, oc:FileExists,
     oc:DirectoryWritable, oc:APIKeySet, oc:ToolInstalled, oc:EnvironmentReady
   - Create novel URIs for domain-specific states: oc:DocumentCreated, oc:NetworkScanned

2. **yieldsState**: What becomes true AFTER successful execution?
   - Examples: oc:DocumentCreated, oc:NetworkDiscovered, oc:FileDownloaded

3. **handlesFailure**: What states indicate this skill FAILED?
   - Examples: oc:PermissionDenied, oc:NetworkTimeout, oc:FileNotFound, oc:InvalidInput

CRITICAL: Output URIs (oc:StateName), NOT string literals.
```

## 7. Loader Changes (loader.py)

### Remove
- Single monolithic `skills.ttl` output
- Hash-based merge logic (simplified - no merge needed for modular)

### Add
1. `generate_core_ontology()` - Creates `ontoclaw-core.ttl` if missing
2. `serialize_skill_module()` - Outputs individual `skill.ttl`
3. `generate_index_manifest()` - Creates `index.ttl` with all imports
4. `mirror_skill_path()` - Converts `skills/a/b/SKILL.md` → `semantic-skills/a/b/skill.ttl`

## 8. Configuration Summary

| Variable | Default | Description |
|----------|---------|-------------|
| `ONTOCLAW_BASE_URI` | `http://ontoclaw.marea.software/ontology#` | Namespace prefix |
| `ONTOCLAW_SKILLS_DIR` | `../../skills/` | Input directory |
| `ONTOCLAW_OUTPUT_DIR` | `../../semantic-skills/` | Output directory |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6-20250514` | LLM attestation |

## 9. Test Updates

1. `test_loader.py` - Add tests for modular output, path mirroring
2. `test_schemas.py` - Add tests for StateTransition model
3. `test_transformer.py` - Add tests for state extraction prompt
4. Integration test - Compile a skill and verify modular TTL structure

---

## Implementation Order

1. `schemas.py` - Add StateTransition model, remove constraints
2. `transformer.py` - Update prompt, add state extraction
3. `loader.py` - Modular output, path mirroring, core ontology
4. `cli.py` - Update default paths, add `--init-core` command
5. Tests - Update existing, add new modular tests
