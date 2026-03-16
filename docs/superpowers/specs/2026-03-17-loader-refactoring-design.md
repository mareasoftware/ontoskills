# Design: Refactor Loader & Implement Lifecycle Management

**Date:** 2026-03-17
**Status:** Draft
**Author:** Claude

## Problem Statement

The `compiler/loader.py` module has grown to 855 lines and violates the Single Responsibility Principle. It handles:
- Core ontology definition (namespaces, TBox creation)
- Pydantic-to-RDF serialization
- File I/O operations (loading, saving, atomic writes)
- Intelligent merging with hash-based deduplication
- Index manifest generation

Additionally, two lifecycle management features are missing:
1. **Orphan cleanup**: When users delete/rename `.md` files, the corresponding `.ttl` files become orphaned
2. **Cache invalidation**: When SHACL schemas or LLM prompts change, users need a way to force recompilation

## Goals

1. Refactor `loader.py` into smaller, highly cohesive modules
2. Implement orphan cleanup that runs at compile start
3. Implement `--force` flag to bypass hash-based caching
4. Maintain backward compatibility with SHACL validation hooks
5. Keep all 91 selected tests passing (94 total, 3 deselected)
6. Fix pre-existing bug: cli.py passes 3 arguments to 2-parameter function

## Design

### 1. Module Structure

Split `loader.py` into 3 focused modules:

#### `compiler/core_ontology.py` (~120 lines)

**Responsibilities:**
- Namespace management
- Core ontology (TBox) creation

**Functions:**
- `get_oc_namespace() -> Namespace` - Returns the OntoClaw namespace
- `create_core_ontology(output_path: Path | None = None) -> Graph` - Creates ontoclaw-core.ttl

**Imports:**
- `rdflib` (Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef)
- `rdflib.namespace` (DCTERMS, SKOS, PROV)
- `datetime`, `logging`
- `compiler.config` (BASE_URI, CORE_STATES, FAILURE_STATES, OUTPUT_DIR)

---

#### `compiler/serialization.py` (~150 lines)

**Responsibilities:**
- Convert Pydantic `ExtractedSkill` models to RDF triples
- Create standalone skill.ttl module files
- SHACL validation gatekeeper (MUST remain integrated)

**Functions:**
- `serialize_skill(graph: Graph, skill: ExtractedSkill) -> None` - Adds skill triples to graph
- `serialize_skill_to_module(skill: ExtractedSkill, output_path: Path, output_base: Path | None = None) -> None` - Creates skill.ttl file
  - **MODIFIED**: Added `output_base` parameter (defaults to None, uses OUTPUT_DIR config)
  - This fixes a pre-existing bug where cli.py passed 3 arguments to a 2-parameter function

**Imports:**
- `rdflib` (Graph, RDF, RDFS, OWL, Literal, URIRef)
- `rdflib.namespace` (DCTERMS, SKOS, PROV)
- `hashlib`, `logging`
- `compiler.core_ontology` (get_oc_namespace)
- `compiler.validator` (validate_and_raise)
- `compiler.schemas` (ExtractedSkill)
- `compiler.exceptions` (OntologyValidationError)
- `compiler.config` (OUTPUT_DIR)

**Critical:** `serialize_skill_to_module()` MUST call `validate_and_raise()` before writing. This is the SHACL gatekeeper.

---

#### `compiler/storage.py` (~350 lines)

**Responsibilities:**
- Path mirroring operations
- File loading and atomic saving
- Intelligent merging with hash deduplication
- Index manifest generation
- Orphan cleanup

**Functions:**
- `mirror_skill_path(skill_dir: Path, output_base: Path) -> Path`
- `get_output_path(skill_dir: Path, output_base: Path | None) -> Path`
- `create_output_directory(skill_dir: Path, output_base: Path | None) -> Path`
- `load_skill_module(module_path: Path) -> Graph`
- `load_ontology(ontology_path: Path) -> Graph`
- `get_hash_mapping(graph: Graph) -> dict[str, URIRef]`
- `get_id_mapping(graph: Graph) -> dict[str, URIRef]`
- `remove_skill(graph: Graph, skill_uri: URIRef) -> None`
- `merge_skill(ontology_path: Path, skill: ExtractedSkill, force: bool = False) -> Graph` - **MODIFIED**: Adds `force` parameter
- `save_ontology_atomic(ontology_path: Path, graph: Graph, backup_dir: Path | None, max_backups: int) -> None`
- `apply_reasoning(graph: Graph) -> Graph`
- `generate_index_manifest(skill_paths: list[Path], index_path: Path, output_base: Path | None) -> None`
- **NEW**: `clean_orphaned_skills(skills_dir: Path, output_dir: Path, dry_run: bool = False) -> int`

**Imports:**
- `rdflib`, `owlrl`, `hashlib`, `shutil`, `logging`
- `datetime`, `pathlib`, `typing`
- `compiler.core_ontology` (get_oc_namespace)
- `compiler.serialization` (serialize_skill)
- `compiler.validator` (validate_and_raise)
- `compiler.schemas` (ExtractedSkill)
- `compiler.exceptions` (OntologyLoadError, OntologyValidationError)
- `compiler.config` (BASE_URI, SKILLS_DIR, OUTPUT_DIR)

---

### 2. Orphan Cleanup

**Algorithm:**

```python
def clean_orphaned_skills(
    skills_dir: Path,
    output_dir: Path,
    dry_run: bool = False
) -> int:
    """
    Remove .ttl files whose source SKILL.md no longer exists.

    Args:
        skills_dir: Path to skills/ directory
        output_dir: Path to semantic-skills/ directory
        dry_run: If True, log what would be deleted without deleting

    Returns:
        Count of orphaned files removed
    """
    orphans_removed = 0

    # Find all skill.ttl files in output directory
    for ttl_file in output_dir.rglob("skill.ttl"):
        # Compute expected SKILL.md path
        rel_path = ttl_file.parent.relative_to(output_dir)
        skill_md = skills_dir / rel_path / "SKILL.md"

        # If source doesn't exist, this is an orphan
        if not skill_md.exists():
            logger.info(f"Orphan found: {ttl_file} (source: {skill_md} missing)")
            if not dry_run:
                ttl_file.unlink()
            orphans_removed += 1

    return orphans_removed
```

**Integration:**
- Called at the start of `compile` command in `cli.py`
- Runs before any skill processing
- Logs all orphans found/removed

---

### 3. Cache Invalidation (`--force` flag)

**CLI Changes:**

```python
@cli.command()
@click.option('-f', '--force', is_flag=True,
              help='Force recompilation of all skills (bypass cache)')
def compile(ctx, skill_name, input_dir, output_dir, dry_run, skip_security, yes, force, verbose, quiet):
    ...
```

**Behavior:**
1. Run orphan cleanup (always)
2. If `--force` is set, skip hash comparison in `merge_skill()`
3. Re-extract all skills regardless of content hash
4. Overwrite all .ttl files

**Implementation in `merge_skill()`:**

```python
def merge_skill(
    ontology_path: Path,
    skill: ExtractedSkill,
    force: bool = False
) -> Graph:
    graph = load_ontology(ontology_path)
    hash_mapping = get_hash_mapping(graph)
    id_mapping = get_id_mapping(graph)

    # Skip hash check if force is True
    if not force and skill.hash in hash_mapping:
        logger.info(f"Skill {skill.id} unchanged (hash match), skipping")
        return graph

    # ... rest of merge logic
```

**Threading through:**
- `cli.py` passes `force` to compilation loop
- Each skill extraction checks `force` before skipping

---

### 4. Import Updates

**`compiler/cli.py`:**

```python
# Before:
from compiler.loader import (
    create_core_ontology,
    serialize_skill_to_module,
    generate_index_manifest,
    get_oc_namespace,
)

# After:
from compiler.core_ontology import get_oc_namespace, create_core_ontology
from compiler.serialization import serialize_skill_to_module
from compiler.storage import (
    generate_index_manifest,
    clean_orphaned_skills,
    merge_skill,
)
```

**`compiler/tests/`:**

- `test_loader.py` → split into:
  - `test_core_ontology.py`
  - `test_serialization.py`
  - `test_storage.py`
- **Fix incorrect import** in `test_load_skill_module_not_found`:
  - `from loader import OntologyLoadError` → `from compiler.exceptions import OntologyLoadError`

---

### 5. Testing Strategy

**New Tests:**

| Test | File | Purpose |
|------|------|---------|
| `test_clean_orphaned_skills_removes_orphan` | `test_storage.py` | Verify orphan detection |
| `test_clean_orphaned_skills_preserves_valid` | `test_storage.py` | Verify non-orphan preservation |
| `test_clean_orphaned_skills_dry_run` | `test_storage.py` | Verify dry run doesn't delete |
| `test_force_flag_bypasses_hash` | `test_cli.py` | Verify --force skips hash check |
| `test_force_flag_with_compile` | `test_cli.py` | Verify --force with full compile |

**Existing Tests:**

- 91 tests must remain green
- Critical: SHACL validation tests in `test_validation.py` test the gatekeeper
- The gatekeeper is called in `serialize_skill_to_module()` which moves to `serialization.py`

---

### 6. File Changes Summary

**Files to Create:**

| File | Lines | Purpose |
|------|-------|---------|
| `compiler/core_ontology.py` | ~120 | Namespace + core ontology |
| `compiler/serialization.py` | ~150 | RDF serialization |
| `compiler/storage.py` | ~350 | File I/O, merging, cleanup |

**Files to Modify:**

| File | Changes |
|------|---------|
| `compiler/cli.py` | Update imports, add `--force` flag, call `clean_orphaned_skills()` |
| `compiler/tests/test_loader.py` | Split into 3 files, add new tests |

**Files to Delete:**

| File | Reason |
|------|--------|
| `compiler/loader.py` | Replaced by 3 focused modules |

---

## Implementation Order

1. Create `core_ontology.py` with namespace and ontology functions
2. Create `serialization.py` with serialize functions
3. Create `storage.py` with file I/O, merging, and new cleanup function
4. Update `cli.py` with new imports and `--force` flag
5. Split `test_loader.py` into 3 test files
6. Add new tests for orphan cleanup and `--force`
7. Delete `loader.py`
8. Run full test suite to verify all 91 tests pass

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking SHACL validation | Gatekeeper stays in `serialize_skill_to_module()`, tests verify |
| Breaking existing imports | Update all imports in `cli.py`, `validator.py`, tests |
| Orphan cleanup deletes wrong files | Use relative path computation, add dry-run mode |
| `--force` breaks idempotency | Log when force is active, tests verify behavior |
| cli.py passes extra argument to serialize_skill_to_module | Add `output_base` parameter with default, verify signature matches call site |

---

## Success Criteria

- [ ] `loader.py` replaced by 3 focused modules
- [ ] All imports updated across codebase
- [ ] `clean_orphaned_skills()` function implemented
- [ ] Orphan cleanup runs at compile start
- [ ] `--force` flag added to CLI
- [ ] `--force` bypasses hash checks
- [ ] All 91 selected tests pass (94 total, 3 deselected)
- [ ] New tests for orphan cleanup added
- [ ] New tests for `--force` flag added
- [ ] SHACL validation gatekeeper remains functional
- [ ] Pre-existing bug fixed: `serialize_skill_to_module` signature matches call site
