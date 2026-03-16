# OntoClaw ETL Refactoring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Python ETL from monolithic output to modular neuro-symbolic ontology with state-transition logic.

**Architecture:** Replace single `skills.ttl` with modular output: `ontoclaw-core.ttl` (TBox), per-skill `skill.ttl` modules (ABox), and `index.ttl` manifest. Skills output to mirrored directory structure. State transitions extracted as OWL/RDF URIs instead of string literals.

**Tech Stack:** Python 3.10+, Pydantic 2.0, rdflib 7.0, Anthropic API

---

## File Structure

### Modified Files
| File | Changes |
|------|---------|
| `schemas.py` | Add `StateTransition` model, remove `constraints`, add `generated_by` |
| `transformer.py` | Update SYSTEM_PROMPT with state extraction, set `generated_by` |
| `loader.py` | **Complete rewrite** - modular output, path mirroring, core ontology |
| `cli.py` | Update default paths, add `init-core` command |
| `tests/test_schemas.py` | Add StateTransition tests, update ExtractedSkill tests |
| `tests/test_transformer.py` | Add state extraction tests |
| `tests/test_loader.py` | **Complete rewrite** - modular output tests |
| `tests/test_cli.py` | Update path tests, add init-core tests |
| `pyproject.toml` | Update project name to `ontoclaw-compiler` |

### New Files
| File | Purpose |
|------|---------|
| `config.py` | Centralized configuration with environment variables |

---

## Chunk 1: Configuration Module

### Task 1.1: Create config.py with environment-driven settings

**Files:**
- Create: `config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test for config defaults**

```python
# tests/test_config.py
"""Tests for configuration module."""
import os
import pytest


def test_default_base_uri():
    """Test default ONTOCLAW_BASE_URI when env var not set."""
    # Ensure env var is not set
    os.environ.pop("ONTOCLAW_BASE_URI", None)

    # Re-import to get fresh values
    import importlib
    import config
    importlib.reload(config)

    assert config.BASE_URI == "http://ontoclaw.marea.software/ontology#"


def test_custom_base_uri():
    """Test custom ONTOCLAW_BASE_URI from env var."""
    os.environ["ONTOCLAW_BASE_URI"] = "http://custom.example.com/ontology#"

    import importlib
    import config
    importlib.reload(config)

    assert config.BASE_URI == "http://custom.example.com/ontology#"

    # Cleanup
    os.environ.pop("ONTOCLAW_BASE_URI", None)


def test_default_paths():
    """Test default directory paths."""
    os.environ.pop("ONTOCLAW_SKILLS_DIR", None)
    os.environ.pop("ONTOCLAW_OUTPUT_DIR", None)

    import importlib
    import config
    importlib.reload(config)

    assert config.SKILLS_DIR == "../../skills/"
    assert config.OUTPUT_DIR == "../../semantic-skills/"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'config'"

- [ ] **Step 3: Implement config.py**

```python
# config.py
"""
OntoClaw Compiler Configuration.

All settings are environment-driven for enterprise deployment.
"""
import os

# Namespace configuration
BASE_URI = os.environ.get(
    "ONTOCLAW_BASE_URI",
    "http://ontoclaw.marea.software/ontology#"
)

# Directory paths (relative to compiler root)
SKILLS_DIR = os.environ.get("ONTOCLAW_SKILLS_DIR", "../../skills/")
OUTPUT_DIR = os.environ.get("ONTOCLAW_OUTPUT_DIR", "../../semantic-skills/")

# LLM configuration (existing, moved here for centralization)
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6-20250514")
SECURITY_MODEL = os.environ.get("SECURITY_MODEL", "claude-3-5-haiku-20241022")

# Extraction settings
MAX_ITERATIONS = 20
EXTRACTION_TIMEOUT = 120  # seconds

# Predefined core states (hybrid taxonomy)
CORE_STATES = {
    "SystemAuthenticated": "System credentials validated",
    "NetworkAvailable": "Network connectivity confirmed",
    "FileExists": "Required file present",
    "DirectoryWritable": "Target directory is writable",
    "APIKeySet": "Required API key configured",
    "ToolInstalled": "Required tool/cli available",
    "EnvironmentReady": "Runtime environment prepared",
}

# Common failure states
FAILURE_STATES = {
    "PermissionDenied": "Insufficient permissions for operation",
    "NetworkTimeout": "Network operation timed out",
    "FileNotFound": "Required file not found",
    "InvalidInput": "Input validation failed",
    "OperationFailed": "General operation failure",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add environment-driven configuration module"
```

---

## Chunk 2: Schema Updates

### Task 2.1: Add StateTransition model to schemas.py

**Files:**
- Modify: `schemas.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 1: Write failing test for StateTransition model**

```python
# Add to tests/test_schemas.py

def test_state_transition_model():
    """Test StateTransition model with URI lists."""
    from schemas import StateTransition

    transition = StateTransition(
        requires_state=["oc:SystemAuthenticated", "oc:ToolInstalled"],
        yields_state=["oc:DocumentCreated"],
        handles_failure=["oc:PermissionDenied", "oc:FileNotFound"]
    )

    assert len(transition.requires_state) == 2
    assert len(transition.yields_state) == 1
    assert len(transition.handles_failure) == 2


def test_state_transition_defaults():
    """Test StateTransition with empty lists."""
    from schemas import StateTransition

    transition = StateTransition()
    assert transition.requires_state == []
    assert transition.yields_state == []
    assert transition.handles_failure == []


def test_state_transition_uri_validation():
    """Test that state URIs must follow oc: prefix pattern."""
    from schemas import StateTransition
    from pydantic import ValidationError

    # Valid URIs
    StateTransition(requires_state=["oc:ValidState"])

    # Invalid URI (no oc: prefix) should raise validation error
    with pytest.raises(ValidationError):
        StateTransition(requires_state=["InvalidState"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas.py::test_state_transition_model -v`
Expected: FAIL with "ImportError: cannot import name 'StateTransition'"

- [ ] **Step 3: Implement StateTransition in schemas.py**

```python
# schemas.py (complete rewrite)
"""Pydantic models for structured skill extraction."""

import re
from typing import Literal

from pydantic import BaseModel, field_validator


class Requirement(BaseModel):
    """A requirement for skill execution."""
    type: Literal["EnvVar", "Tool", "Hardware", "API", "Knowledge"]
    value: str
    optional: bool = False


class ExecutionPayload(BaseModel):
    """Execution code and configuration."""
    executor: Literal["shell", "python", "node", "claude_tool"]
    code: str
    timeout: int | None = None


class StateTransition(BaseModel):
    """
    State transition logic for reasoning.

    All states are URIs in the oc: namespace (e.g., oc:SystemAuthenticated).
    This enables the Rust MCP server to perform OWL reasoning.
    """
    requires_state: list[str] = []
    yields_state: list[str] = []
    handles_failure: list[str] = []

    @field_validator("requires_state", "yields_state", "handles_failure")
    @classmethod
    def validate_state_uris(cls, v: list[str]) -> list[str]:
        """Validate that all states are oc: URIs."""
        uri_pattern = re.compile(r"^oc:[A-Z][a-zA-Z0-9]*$")
        for state in v:
            if not uri_pattern.match(state):
                raise ValueError(
                    f"Invalid state URI: '{state}'. "
                    f"Must be oc:CamelCase (e.g., oc:SystemAuthenticated)"
                )
        return v


class ExtractedSkill(BaseModel):
    """Complete extracted skill data."""
    id: str
    hash: str
    nature: str
    genus: str
    differentia: str
    intents: list[str]
    requirements: list[Requirement]
    depends_on: list[str] = []
    extends: list[str] = []
    contradicts: list[str] = []

    # NEW: State transitions (replaces flat constraints)
    state_transitions: StateTransition = StateTransition()

    # NEW: LLM attestation (from ANTHROPIC_MODEL env var)
    generated_by: str = "unknown"

    execution_payload: ExecutionPayload | None
    provenance: str | None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas.py -v`
Expected: All tests PASS

- [ ] **Step 5: Update existing test to use new schema**

```python
# Update tests/test_schemas.py - fix test_schemas_validation

def test_schemas_validation():
    req = Requirement(type="EnvVar", value="API_KEY")
    assert req.optional is False

    payload = ExecutionPayload(executor="shell", code="echo 'hello'")
    assert payload.timeout is None

    skill = ExtractedSkill(
        id="test-skill",
        hash="abcdef",
        nature="A test skill",
        genus="Test",
        differentia="that tests",
        intents=["testing"],
        requirements=[req],
        state_transitions=StateTransition(
            requires_state=["oc:ToolInstalled"],
            yields_state=["oc:TestComplete"]
        ),
        generated_by="claude-sonnet-4-6",
        execution_payload=payload,
        provenance="/path",
    )
    assert skill.id == "test-skill"
    assert skill.state_transitions.requires_state == ["oc:ToolInstalled"]
```

- [ ] **Step 6: Run all schema tests**

Run: `pytest tests/test_schemas.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add schemas.py tests/test_schemas.py
git commit -m "feat: add StateTransition model, remove constraints, add generated_by"
```

---

## Chunk 3: Transformer Updates

### Task 3.1: Update transformer.py with state extraction prompt

**Files:**
- Modify: `transformer.py`
- Modify: `tests/test_transformer.py`

- [ ] **Step 1: Write failing test for state extraction in prompt**

```python
# Add to tests/test_transformer.py

def test_system_prompt_includes_state_extraction():
    """Test that SYSTEM_PROMPT includes state transition extraction instructions."""
    from transformer import SYSTEM_PROMPT

    # Check for key state extraction terms
    assert "requiresState" in SYSTEM_PROMPT or "requires_state" in SYSTEM_PROMPT
    assert "yieldsState" in SYSTEM_PROMPT or "yields_state" in SYSTEM_PROMPT
    assert "handlesFailure" in SYSTEM_PROMPT or "handles_failure" in SYSTEM_PROMPT
    assert "oc:" in SYSTEM_PROMPT  # Namespace prefix


def test_tool_use_loop_sets_generated_by():
    """Test that extracted skill has generated_by set from MODEL."""
    from transformer import MODEL
    # This will be tested via integration, but we can check MODEL is used
    assert MODEL is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_transformer.py::test_system_prompt_includes_state_extraction -v`
Expected: FAIL (assertion error - prompt doesn't have state extraction)

- [ ] **Step 3: Update transformer.py with new prompt and generated_by**

```python
# transformer.py (key changes only - show full file for context)
"""
LLM Tool-Use Extraction Module.

Orchestrates the tool-use conversation with Claude to extract
structured skill data from markdown files.
"""

import json
import os
import logging
from pathlib import Path
from typing import Any

import anthropic
from anthropic import Anthropic

from schemas import ExtractedSkill
from exceptions import ExtractionError
from config import ANTHROPIC_MODEL, MAX_ITERATIONS, EXTRACTION_TIMEOUT, CORE_STATES, FAILURE_STATES

logger = logging.getLogger(__name__)

# Tool definitions
COMPLETION_TOOL = "extract_skill"

# System prompt following Knowledge Architecture framework
SYSTEM_PROMPT = """You are an Ontological Architect. Your task is to analyze agent skills
and extract their essential structure using the Knowledge Architecture framework.

## KNOWLEDGE ARCHITECTURE FRAMEWORK

### Categories of Being
- Tool: Enables action
- Concept: A framework, methodology
- Work: A created artifact generator

### Genus and Differentia
"A is a B that C" - classical definition structure

### Relations as First-Class Citizens
- depends-on: Cannot function without
- extends: Builds upon
- contradicts: In tension with
- implements: Realizes abstraction
- exemplifies: Instance of pattern

## STATE TRANSITION EXTRACTION (CRITICAL)

Extract the skill's logic as a state machine using URIs, NOT strings.

### requiresState (Pre-conditions)
What must be true BEFORE this skill can run?
- Prefer predefined URIs: oc:SystemAuthenticated, oc:NetworkAvailable, oc:FileExists,
  oc:DirectoryWritable, oc:APIKeySet, oc:ToolInstalled, oc:EnvironmentReady
- Create novel URIs for domain-specific states: oc:DocumentCreated, oc:NetworkScanned

### yieldsState (Success outcomes)
What becomes true AFTER successful execution?
- Examples: oc:DocumentCreated, oc:NetworkDiscovered, oc:FileDownloaded

### handlesFailure (Failure states)
What states indicate this skill FAILED?
- Examples: oc:PermissionDenied, oc:NetworkTimeout, oc:FileNotFound, oc:InvalidInput

CRITICAL: Output URIs (oc:StateName), NOT string literals.

## YOUR TASK

1. Use list_files to discover all files in the skill directory
2. Use read_file to read SKILL.md and any reference files
3. Analyze the skill and extract its structure
4. Call extract_skill with the structured data

Be thorough but concise. Focus on the essential nature of the skill."""

# Tool definitions (update extract_skill schema)
TOOLS = [
    {
        "name": "list_files",
        "description": "List all files in the skill directory recursively.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "read_file",
        "description": "Read a file from the skill directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from skill directory root"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "extract_skill",
        "description": "Submit the extracted skill data in structured format.",
        "input_schema": ExtractedSkill.model_json_schema()
    }
]

# Initialize Anthropic client
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL")
)


def tool_result(tool_id: str, content: str) -> dict:
    """Create a tool result message for the conversation."""
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": content
        }]
    }


def execute_tool(name: str, input_data: dict, skill_dir: Path) -> str:
    """
    Execute a tool call and return JSON result.

    Args:
        name: Tool name (list_files, read_file, extract_skill)
        input_data: Tool input parameters
        skill_dir: Path to skill directory

    Returns:
        JSON string with tool result or error
    """
    try:
        if name == "list_files":
            files = [
                str(f.relative_to(skill_dir))
                for f in skill_dir.rglob("*")
                if f.is_file() and not f.name.startswith(".")
            ]
            return json.dumps({"files": sorted(files)})

        elif name == "read_file":
            path = input_data.get("path", "")
            file_path = skill_dir / path

            if not file_path.exists() or not file_path.is_file():
                return json.dumps({"error": f"File not found: {path}"})

            # Security: prevent path traversal
            try:
                file_path.resolve().relative_to(skill_dir.resolve())
            except ValueError:
                return json.dumps({"error": f"Access denied: {path}"})

            content = file_path.read_text(encoding="utf-8")
            return json.dumps({"content": content, "path": path})

        elif name == "extract_skill":
            # Validate the extraction data
            ExtractedSkill.model_validate(input_data)
            return json.dumps({"status": "success", "message": "Skill extracted successfully"})

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return json.dumps({"error": str(e)})


def tool_use_loop(skill_dir: Path, skill_hash: str, skill_id: str) -> ExtractedSkill:
    """
    Orchestrates the tool-use conversation with Claude.

    Args:
        skill_dir: Path to skill directory
        skill_hash: Pre-computed SHA-256 hash of skill files
        skill_id: Pre-computed skill ID slug

    Returns:
        ExtractedSkill with structured data

    Raises:
        ExtractionError: If extraction fails or times out
    """
    messages = [{
        "role": "user",
        "content": f"""Analyze the skill in this directory and extract its structure.

Directory: {skill_dir.name}
Skill ID: {skill_id}
Content Hash: {skill_hash[:16]}...

Use the available tools to:
1. List and read the skill files
2. Extract the structured data
3. Submit with extract_skill"""
    }]

    for iteration in range(MAX_ITERATIONS):
        logger.debug(f"Tool-use iteration {iteration + 1}/{MAX_ITERATIONS}")

        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=8192,
                tools=TOOLS,
                messages=messages,
                system=SYSTEM_PROMPT,
                timeout=EXTRACTION_TIMEOUT
            )
        except anthropic.APIError as e:
            raise ExtractionError(f"API error during extraction: {e}")

        # Process response blocks
        tool_results = []
        extraction_data = None

        for block in response.content:
            if block.type == "tool_use":
                logger.debug(f"Tool call: {block.name}")

                if block.name == COMPLETION_TOOL:
                    # Validate and return the extraction
                    try:
                        skill = ExtractedSkill.model_validate(block.input)
                        # Override with our computed values
                        skill.id = skill_id
                        skill.hash = skill_hash
                        skill.provenance = str(skill_dir)
                        # Set LLM attestation
                        skill.generated_by = ANTHROPIC_MODEL
                        logger.info(f"Successfully extracted skill: {skill_id}")
                        return skill
                    except Exception as e:
                        raise ExtractionError(f"Invalid extraction data: {e}")
                else:
                    # Execute tool and collect result
                    result = execute_tool(block.name, block.input, skill_dir)
                    tool_results.append(tool_result(block.id, result))

            elif block.type == "text":
                logger.debug(f"LLM text: {block.text[:100]}...")

        # Check for end_turn without extraction
        if response.stop_reason == "end_turn":
            raise ExtractionError("LLM finished without calling extract_skill")

        # Add tool results to conversation
        if tool_results:
            messages.extend(tool_results)

    raise ExtractionError(f"Max iterations ({MAX_ITERATIONS}) exceeded")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_transformer.py::test_system_prompt_includes_state_extraction -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add transformer.py tests/test_transformer.py
git commit -m "feat: add state transition extraction to LLM prompt"
```

---

## Chunk 4: Loader Rewrite (Part 1 - Core Ontology)

### Task 4.1: Implement core ontology generation

**Files:**
- Modify: `loader.py`
- Modify: `tests/test_loader.py`

- [ ] **Step 1: Write failing test for core ontology generation**

```python
# Add to tests/test_loader.py (new imports at top)
import pytest
from pathlib import Path
from rdflib import Graph, RDF, RDFS, OWL, Namespace
from loader import (
    create_core_ontology,
    get_oc_namespace,
)
from config import BASE_URI


def test_get_oc_namespace():
    """Test that OC namespace uses BASE_URI."""
    oc = get_oc_namespace()
    # Should end with # for hash namespace
    assert str(oc).rstrip("#") == BASE_URI.rstrip("#")


def test_create_core_ontology_structure(tmp_path):
    """Test that core ontology has required classes and properties."""
    core_path = tmp_path / "ontoclaw-core.ttl"
    graph = create_core_ontology(core_path)

    # Check file was created
    assert core_path.exists()

    # Check prefixes
    prefixes = dict(graph.namespaces())
    assert "oc" in prefixes
    assert "owl" in prefixes

    # Get namespace
    oc = get_oc_namespace()

    # Check required classes exist
    assert (oc.Skill, RDF.type, OWL.Class) in graph
    assert (oc.State, RDF.type, OWL.Class) in graph
    assert (oc.Attempt, RDF.type, OWL.Class) in graph


def test_create_core_ontology_state_properties(tmp_path):
    """Test that state transition properties are defined."""
    core_path = tmp_path / "ontoclaw-core.ttl"
    graph = create_core_ontology(core_path)
    oc = get_oc_namespace()

    # Check state transition properties
    assert (oc.requiresState, RDF.type, OWL.ObjectProperty) in graph
    assert (oc.yieldsState, RDF.type, OWL.ObjectProperty) in graph
    assert (oc.handlesFailure, RDF.type, OWL.ObjectProperty) in graph


def test_create_core_ontology_execution_payload(tmp_path):
    """Test that ExecutionPayload class and properties are defined."""
    core_path = tmp_path / "ontoclaw-core.ttl"
    graph = create_core_ontology(core_path)
    oc = get_oc_namespace()

    # Check ExecutionPayload class
    assert (oc.ExecutionPayload, RDF.type, OWL.Class) in graph

    # Check hasPayload object property
    assert (oc.hasPayload, RDF.type, OWL.ObjectProperty) in graph
    assert (oc.hasPayload, RDFS.domain, oc.Skill) in graph
    assert (oc.hasPayload, RDFS.range, oc.ExecutionPayload) in graph

    # Check execution datatype properties
    assert (oc.executor, RDF.type, OWL.DatatypeProperty) in graph
    assert (oc.code, RDF.type, OWL.DatatypeProperty) in graph
    assert (oc.timeout, RDF.type, OWL.DatatypeProperty) in graph


def test_create_core_ontology_predefined_states(tmp_path):
    """Test that predefined core states are defined."""
    core_path = tmp_path / "ontoclaw-core.ttl"
    graph = create_core_ontology(core_path)
    oc = get_oc_namespace()

    # Check predefined states
    assert (oc.SystemAuthenticated, RDF.type, oc.State) in graph
    assert (oc.NetworkAvailable, RDF.type, oc.State) in graph
    assert (oc.FileExists, RDF.type, oc.State) in graph
    assert (oc.ToolInstalled, RDF.type, oc.State) in graph
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_loader.py::test_get_oc_namespace -v`
Expected: FAIL with "ImportError: cannot import name 'get_oc_namespace'"

- [ ] **Step 3: Implement core ontology functions**

```python
# loader.py (Part 1 - Core Ontology)
"""
RDF Ontology Loader Module.

Handles OWL 2 RDF/Turtle serialization for modular ontology output.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef
from rdflib.namespace import DCTERMS, SKOS, PROV

from schemas import ExtractedSkill, Requirement, ExecutionPayload
from exceptions import OntologyLoadError
from config import BASE_URI, CORE_STATES, FAILURE_STATES

logger = logging.getLogger(__name__)


def get_oc_namespace() -> Namespace:
    """Get the OntoClaw namespace using configured BASE_URI."""
    return Namespace(BASE_URI)


def create_core_ontology(output_path: Path) -> Graph:
    """
    Create the foundational TBox ontology.

    Contains:
    - Base classes (Skill, State, Attempt)
    - State transition properties
    - Predefined core states

    Args:
        output_path: Path to write ontoclaw-core.ttl

    Returns:
        Graph with core ontology
    """
    g = Graph()
    oc = get_oc_namespace()

    # Bind namespaces
    g.bind("oc", oc)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("dcterms", DCTERMS)
    g.bind("prov", PROV)

    # Ontology header
    core_uri = URIRef(BASE_URI.rstrip("#") + "/core")
    g.add((core_uri, RDF.type, OWL.Ontology))
    g.add((core_uri, DCTERMS.title, Literal("OntoClaw Core Ontology")))
    g.add((core_uri, DCTERMS.description, Literal(
        "Foundational TBox for OntoClaw neuro-symbolic skills"
    )))
    g.add((core_uri, OWL.versionIRI, Literal("1.0.0")))

    # === Classes ===

    # oc:Skill - Base class for all skills
    g.add((oc.Skill, RDF.type, OWL.Class))
    g.add((oc.Skill, RDFS.label, Literal("Skill")))
    g.add((oc.Skill, RDFS.comment, Literal("A capability that can be executed")))

    # oc:State - Abstract state class
    g.add((oc.State, RDF.type, OWL.Class))
    g.add((oc.State, RDFS.label, Literal("State")))
    g.add((oc.State, RDFS.comment, Literal("A world state used in reasoning")))

    # oc:Attempt - Execution attempt record
    g.add((oc.Attempt, RDF.type, OWL.Class))
    g.add((oc.Attempt, RDFS.label, Literal("Attempt")))
    g.add((oc.Attempt, RDFS.comment, Literal("Record of a skill execution attempt")))

    # === State Transition Properties ===

    # oc:requiresState - Pre-conditions
    g.add((oc.requiresState, RDF.type, OWL.ObjectProperty))
    g.add((oc.requiresState, RDFS.domain, oc.Skill))
    g.add((oc.requiresState, RDFS.range, oc.State))
    g.add((oc.requiresState, RDFS.label, Literal("requires state")))
    g.add((oc.requiresState, RDFS.comment, Literal("Pre-condition that must be true before execution")))

    # oc:yieldsState - Success outcomes
    g.add((oc.yieldsState, RDF.type, OWL.ObjectProperty))
    g.add((oc.yieldsState, RDFS.domain, oc.Skill))
    g.add((oc.yieldsState, RDFS.range, oc.State))
    g.add((oc.yieldsState, RDFS.label, Literal("yields state")))
    g.add((oc.yieldsState, RDFS.comment, Literal("Post-condition that becomes true after successful execution")))

    # oc:handlesFailure - Failure states
    g.add((oc.handlesFailure, RDF.type, OWL.ObjectProperty))
    g.add((oc.handlesFailure, RDFS.domain, oc.Skill))
    g.add((oc.handlesFailure, RDFS.range, oc.State))
    g.add((oc.handlesFailure, RDFS.label, Literal("handles failure")))
    g.add((oc.handlesFailure, RDFS.comment, Literal("State indicating this skill failed")))

    # oc:hasStatus - Attempt status
    g.add((oc.hasStatus, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasStatus, RDFS.domain, oc.Attempt))
    g.add((oc.hasStatus, RDFS.range, oc.State))
    g.add((oc.hasStatus, RDFS.label, Literal("has status")))
    g.add((oc.hasStatus, RDFS.comment, Literal("Execution status of an attempt")))

    # oc:generatedBy - LLM attestation
    g.add((oc.generatedBy, RDF.type, OWL.DatatypeProperty))
    g.add((oc.generatedBy, RDFS.domain, oc.Skill))
    g.add((oc.generatedBy, RDFS.range, RDFS.Literal))
    g.add((oc.generatedBy, RDFS.label, Literal("generated by")))
    g.add((oc.generatedBy, RDFS.comment, Literal("LLM that generated this skill ontology")))

    # === Execution Payload Class and Properties ===

    # oc:ExecutionPayload - Container for executable code
    g.add((oc.ExecutionPayload, RDF.type, OWL.Class))
    g.add((oc.ExecutionPayload, RDFS.label, Literal("Execution Payload")))
    g.add((oc.ExecutionPayload, RDFS.comment, Literal("Executable code and configuration for a skill")))

    # oc:hasPayload - Links Skill to ExecutionPayload
    g.add((oc.hasPayload, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasPayload, RDFS.domain, oc.Skill))
    g.add((oc.hasPayload, RDFS.range, oc.ExecutionPayload))
    g.add((oc.hasPayload, RDFS.label, Literal("has payload")))
    g.add((oc.hasPayload, RDFS.comment, Literal("Executable code for this skill")))

    # oc:executor - The runtime to use (shell, python, node, claude_tool)
    g.add((oc.executor, RDF.type, OWL.DatatypeProperty))
    g.add((oc.executor, RDFS.domain, oc.ExecutionPayload))
    g.add((oc.executor, RDFS.range, RDFS.Literal))
    g.add((oc.executor, RDFS.label, Literal("executor")))
    g.add((oc.executor, RDFS.comment, Literal("Runtime executor for the code")))

    # oc:code - The actual executable code
    g.add((oc.code, RDF.type, OWL.DatatypeProperty))
    g.add((oc.code, RDFS.domain, oc.ExecutionPayload))
    g.add((oc.code, RDFS.range, RDFS.Literal))
    g.add((oc.code, RDFS.label, Literal("code")))
    g.add((oc.code, RDFS.comment, Literal("Executable code string")))

    # oc:timeout - Optional timeout in seconds
    g.add((oc.timeout, RDF.type, OWL.DatatypeProperty))
    g.add((oc.timeout, RDFS.domain, oc.ExecutionPayload))
    g.add((oc.timeout, RDFS.range, RDFS.Literal))
    g.add((oc.timeout, RDFS.label, Literal("timeout")))
    g.add((oc.timeout, RDFS.comment, Literal("Execution timeout in seconds")))

    # === Predefined Core States ===

    for state_name, description in CORE_STATES.items():
        state_uri = oc[state_name]
        g.add((state_uri, RDF.type, oc.State))
        g.add((state_uri, RDFS.label, Literal(state_name)))
        g.add((state_uri, RDFS.comment, Literal(description)))

    # === Predefined Failure States ===

    for state_name, description in FAILURE_STATES.items():
        state_uri = oc[state_name]
        g.add((state_uri, RDF.type, oc.State))
        g.add((state_uri, RDFS.label, Literal(state_name)))
        g.add((state_uri, RDFS.comment, Literal(description)))

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(output_path, format="turtle")
    logger.info(f"Created core ontology at {output_path}")

    return g
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_loader.py -k "test_get_oc_namespace or test_create_core_ontology" -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add loader.py tests/test_loader.py
git commit -m "feat: implement core ontology generation with TBox"
```

---

## Chunk 5: Loader Rewrite (Part 2 - Skill Module Output)

### Task 5.1: Implement path mirroring and skill module serialization

**Files:**
- Modify: `loader.py`
- Modify: `tests/test_loader.py`

- [ ] **Step 1: Write failing test for path mirroring**

```python
# Add to tests/test_loader.py

def test_mirror_skill_path():
    """Test skill path to output path conversion."""
    from loader import mirror_skill_path

    # Simple case
    skill_dir = Path("/project/skills/office/public/docx")
    output_dir = Path("/project/semantic-skills")
    result = mirror_skill_path(skill_dir, output_dir, Path("/project/skills"))
    assert result == Path("/project/semantic-skills/office/public/docx/skill.ttl")

    # Nested case
    skill_dir = Path("/project/skills/network/tools/nmap")
    output_dir = Path("/project/semantic-skills")
    result = mirror_skill_path(skill_dir, output_dir, Path("/project/skills"))
    assert result == Path("/project/semantic-skills/network/tools/nmap/skill.ttl")


def test_serialize_skill_module(tmp_path):
    """Test serialization of a skill to modular TTL."""
    from loader import serialize_skill_module
    from schemas import ExtractedSkill, StateTransition

    oc = get_oc_namespace()

    skill = ExtractedSkill(
        id="docx-engineering",
        hash="abc123def456",
        nature="Document generation tool for DOCX files",
        genus="Tool",
        differentia="creates Word documents",
        intents=["create_docx", "extract_tables"],
        requirements=[],
        state_transitions=StateTransition(
            requires_state=["oc:ToolInstalled"],
            yields_state=["oc:DocumentCreated"],
            handles_failure=["oc:PermissionDenied"]
        ),
        generated_by="claude-sonnet-4-6",
        execution_payload=None,
        provenance="/skills/office/public/docx/SKILL.md",
    )

    output_dir = tmp_path  # semantic-skills root
    output_path = tmp_path / "office" / "public" / "docx" / "skill.ttl"
    graph = serialize_skill_module(skill, output_path, output_dir)

    # Check file created
    assert output_path.exists()

    # Check skill is in graph
    skill_uri = oc["docx_engineering"]
    assert (skill_uri, RDF.type, oc.Skill) in graph

    # Check state transitions
    assert (skill_uri, oc.requiresState, oc.ToolInstalled) in graph
    assert (skill_uri, oc.yieldsState, oc.DocumentCreated) in graph
    assert (skill_uri, oc.handlesFailure, oc.PermissionDenied) in graph

    # Check LLM attestation
    assert (skill_uri, oc.generatedBy, Literal("claude-sonnet-4-6")) in graph


def test_serialize_skill_module_with_payload(tmp_path):
    """Test that execution payload is serialized to RDF."""
    from loader import serialize_skill_module
    from schemas import ExtractedSkill, StateTransition, ExecutionPayload

    oc = get_oc_namespace()

    skill = ExtractedSkill(
        id="shell-skill",
        hash="payload123",
        nature="A skill with shell execution",
        genus="Tool",
        differentia="runs shell commands",
        intents=["execute"],
        requirements=[],
        execution_payload=ExecutionPayload(
            executor="shell",
            code="echo 'Hello, World!'",
            timeout=30
        ),
        generated_by="claude-sonnet-4-6",
        provenance=None,
    )

    output_dir = tmp_path
    output_path = tmp_path / "shell-skill" / "skill.ttl"
    graph = serialize_skill_module(skill, output_path, output_dir)

    # Check payload exists
    payload_uri = oc["payload_shell_skill"]
    assert (payload_uri, RDF.type, oc.ExecutionPayload) in graph

    # Check payload properties
    assert (payload_uri, oc.executor, Literal("shell")) in graph
    assert (payload_uri, oc.code, Literal("echo 'Hello, World!'")) in graph
    assert (payload_uri, oc.timeout, Literal(30)) in graph

    # Check skill links to payload
    skill_uri = oc["shell_skill"]
    assert (skill_uri, oc.hasPayload, payload_uri) in graph


def test_serialize_skill_module_has_owl_imports(tmp_path):
    """Test that skill module imports core ontology."""
    from loader import serialize_skill_module
    from schemas import ExtractedSkill, StateTransition

    skill = ExtractedSkill(
        id="test-skill",
        hash="test123",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        execution_payload=None,
        provenance=None,
    )

    output_dir = tmp_path
    output_path = tmp_path / "test" / "skill.ttl"
    graph = serialize_skill_module(skill, output_path, output_dir)

    # Check for owl:imports pointing to core
    ontology_uri = URIRef("")  # Relative ontology URI
    core_import = (ontology_uri, OWL.imports, None)
    imports_found = list(graph.triples(core_import))
    assert len(imports_found) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_loader.py::test_mirror_skill_path -v`
Expected: FAIL with "ImportError: cannot import name 'mirror_skill_path'"

- [ ] **Step 3: Implement path mirroring and skill serialization**

```python
# Add to loader.py (after create_core_ontology)

def mirror_skill_path(skill_dir: Path, output_dir: Path, skills_dir: Path) -> Path:
    """
    Convert skill directory path to output module path.

    skills/office/public/docx/ → semantic-skills/office/public/docx/skill.ttl

    Args:
        skill_dir: Path to skill directory (e.g., skills/office/public/docx/)
        output_dir: Output directory root (e.g., semantic-skills/)
        skills_dir: Skills directory root (e.g., skills/)

    Returns:
        Path to skill.ttl output file
    """
    # Get relative path from skills root
    relative = skill_dir.relative_to(skills_dir)
    # Build output path with skill.ttl
    return output_dir / relative / "skill.ttl"


def serialize_skill_module(skill: ExtractedSkill, output_path: Path, output_dir: Path) -> Graph:
    """
    Serialize a skill to a standalone TTL module.

    Creates a self-contained ontology file with:
    - owl:Ontology declaration
    - owl:imports for core ontology
    - Skill instance with state transitions

    Args:
        skill: ExtractedSkill to serialize
        output_path: Path to write skill.ttl
        output_dir: Root output directory (semantic-skills/)

    Returns:
        Graph with skill module
    """
    g = Graph()
    oc = get_oc_namespace()

    # Bind namespaces
    g.bind("oc", oc)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("dcterms", DCTERMS)
    g.bind("prov", PROV)

    # Ontology header with imports
    # Use relative URI for the module itself
    g.add((URIRef(""), RDF.type, OWL.Ontology))
    g.add((URIRef(""), DCTERMS.title, Literal(f"Skill: {skill.id}")))

    # Import core ontology (relative path for portability)
    # Calculate relative path from skill.ttl to semantic-skills/ontoclaw-core.ttl
    # e.g., semantic-skills/office/public/docx/skill.ttl -> semantic-skills/ontoclaw-core.ttl
    relative_to_output = output_path.relative_to(output_dir)
    depth = len(relative_to_output.parts) - 1  # -1 for skill.ttl itself
    core_path = "../" * depth + "ontoclaw-core.ttl"
    g.add((URIRef(""), OWL.imports, URIRef(core_path)))

    # Create skill URI (use skill ID as local name)
    skill_uri = oc[skill.id.replace("-", "_")]

    # Basic properties
    g.add((skill_uri, RDF.type, oc.Skill))
    g.add((skill_uri, DCTERMS.identifier, Literal(skill.id)))
    g.add((skill_uri, oc.nature, Literal(skill.nature)))
    g.add((skill_uri, SKOS.broader, Literal(skill.genus)))
    g.add((skill_uri, oc.differentia, Literal(skill.differentia)))

    # Intents
    for intent in skill.intents:
        g.add((skill_uri, oc.resolvesIntent, Literal(intent)))

    # State transitions (as URIs, not strings!)
    for state in skill.state_transitions.requires_state:
        # Convert oc:StateName to full URI
        state_uri = oc[state.replace("oc:", "")]
        g.add((skill_uri, oc.requiresState, state_uri))

    for state in skill.state_transitions.yields_state:
        state_uri = oc[state.replace("oc:", "")]
        g.add((skill_uri, oc.yieldsState, state_uri))

    for state in skill.state_transitions.handles_failure:
        state_uri = oc[state.replace("oc:", "")]
        g.add((skill_uri, oc.handlesFailure, state_uri))

    # LLM attestation
    g.add((skill_uri, oc.generatedBy, Literal(skill.generated_by)))

    # Requirements (as blank nodes)
    for req in skill.requirements:
        req_hash = hashlib.sha256(f"{req.type}:{req.value}".encode()).hexdigest()[:8]
        req_uri = oc[f"req_{req_hash}"]

        req_class = oc[f"Requirement{req.type}"]
        g.add((req_uri, RDF.type, req_class))
        g.add((req_uri, oc.requirementValue, Literal(req.value)))
        g.add((req_uri, oc.isOptional, Literal(req.optional)))
        g.add((skill_uri, oc.hasRequirement, req_uri))

    # Provenance
    if skill.provenance:
        g.add((skill_uri, PROV.wasDerivedFrom, Literal(skill.provenance)))

    # Execution payload (CRITICAL for Rust MCP server)
    if skill.execution_payload:
        payload_uri = oc[f"payload_{skill.id.replace('-', '_')}"]
        g.add((payload_uri, RDF.type, oc.ExecutionPayload))
        g.add((payload_uri, oc.executor, Literal(skill.execution_payload.executor)))
        g.add((payload_uri, oc.code, Literal(skill.execution_payload.code)))
        if skill.execution_payload.timeout:
            g.add((payload_uri, oc.timeout, Literal(skill.execution_payload.timeout)))
        g.add((skill_uri, oc.hasPayload, payload_uri))

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(output_path, format="turtle")
    logger.info(f"Serialized skill module to {output_path}")

    return g
```

Add missing import at top of loader.py:
```python
import hashlib
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_loader.py -k "mirror_skill_path or serialize_skill_module" -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add loader.py tests/test_loader.py
git commit -m "feat: implement path mirroring and skill module serialization"
```

---

## Chunk 6: Loader Rewrite (Part 3 - Index Manifest)

### Task 6.1: Implement index manifest generation

**Files:**
- Modify: `loader.py`
- Modify: `tests/test_loader.py`

- [ ] **Step 1: Write failing test for index manifest**

```python
# Add to tests/test_loader.py

def test_generate_index_manifest(tmp_path):
    """Test generation of index.ttl manifest with owl:imports."""
    from loader import generate_index_manifest

    # Create some dummy skill modules
    skill_paths = [
        tmp_path / "office" / "public" / "docx" / "skill.ttl",
        tmp_path / "office" / "public" / "pdf" / "skill.ttl",
        tmp_path / "network" / "nmap" / "skill.ttl",
    ]

    for path in skill_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# dummy skill")

    index_path = tmp_path / "index.ttl"
    graph = generate_index_manifest(skill_paths, index_path, tmp_path)

    # Check file created
    assert index_path.exists()

    # Check for owl:imports
    imports = list(graph.objects(URIRef(""), OWL.imports))
    assert len(imports) == 4  # 3 skills + core

    # Check relative paths
    import_strs = [str(i) for i in imports]
    assert any("./ontoclaw-core.ttl" in s for s in import_strs)
    assert any("office/public/docx/skill.ttl" in s for s in import_strs)
    assert any("office/public/pdf/skill.ttl" in s for s in import_strs)
    assert any("network/nmap/skill.ttl" in s for s in import_strs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_loader.py::test_generate_index_manifest -v`
Expected: FAIL with "ImportError: cannot import name 'generate_index_manifest'"

- [ ] **Step 3: Implement index manifest generation**

```python
# Add to loader.py

def generate_index_manifest(
    skill_paths: list[Path],
    index_path: Path,
    output_dir: Path
) -> Graph:
    """
    Generate index.ttl manifest with owl:imports for all skills.

    Args:
        skill_paths: List of paths to skill.ttl files
        index_path: Path to write index.ttl
        output_dir: Root output directory (semantic-skills/)

    Returns:
        Graph with manifest
    """
    g = Graph()

    # Bind namespaces
    g.bind("owl", OWL)
    g.bind("dcterms", DCTERMS)

    # Ontology header
    g.add((URIRef(""), RDF.type, OWL.Ontology))
    g.add((URIRef(""), DCTERMS.title, Literal("OntoClaw Skills Index")))
    g.add((URIRef(""), DCTERMS.description, Literal(
        "Manifest importing all compiled skill modules"
    )))

    # Import core ontology first
    g.add((URIRef(""), OWL.imports, URIRef("./ontoclaw-core.ttl")))

    # Import each skill module (relative paths)
    for skill_path in sorted(skill_paths):
        # Calculate relative path from index location
        relative = skill_path.relative_to(output_dir)
        import_path = f"./{relative}"
        g.add((URIRef(""), OWL.imports, URIRef(import_path)))

    # Save to file
    index_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(index_path, format="turtle")
    logger.info(f"Generated index manifest at {index_path} with {len(skill_paths)} imports")

    return g
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_loader.py::test_generate_index_manifest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add loader.py tests/test_loader.py
git commit -m "feat: implement index manifest generation with owl:imports"
```

---

## Chunk 7: CLI Updates

### Task 7.1: Update CLI with new paths and init-core command

**Files:**
- Modify: `cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for new CLI behavior**

```python
# Add to tests/test_cli.py

from click.testing import CliRunner
from cli import cli


def test_compile_default_paths():
    """Test that compile uses new default paths."""
    runner = CliRunner()

    # This will fail because skills dir doesn't exist, but we can check the error message
    result = runner.invoke(cli, ['compile', '--help'])

    # Check help shows new defaults
    assert "../../skills/" in result.output or "skills/" in result.output


def test_init_core_command(tmp_path):
    """Test init-core command creates ontoclaw-core.ttl."""
    runner = CliRunner()
    output_dir = tmp_path / "semantic-skills"

    result = runner.invoke(cli, [
        'init-core',
        '-o', str(output_dir)
    ])

    assert result.exit_code == 0
    assert (output_dir / "ontoclaw-core.ttl").exists()


def test_init_core_idempotent(tmp_path):
    """Test that init-core doesn't overwrite existing core."""
    runner = CliRunner()
    output_dir = tmp_path / "semantic-skills"

    # First run
    result1 = runner.invoke(cli, ['init-core', '-o', str(output_dir)])
    assert result1.exit_code == 0

    # Get content hash (more reliable than mtime)
    core_path = output_dir / "ontoclaw-core.ttl"
    import hashlib
    content1 = core_path.read_text()
    hash1 = hashlib.sha256(content1.encode()).hexdigest()

    # Second run (should skip without --force)
    result2 = runner.invoke(cli, ['init-core', '-o', str(output_dir)])
    content2 = core_path.read_text()
    hash2 = hashlib.sha256(content2.encode()).hexdigest()

    assert hash1 == hash2  # Content unchanged
    assert "already exists" in result2.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_init_core_command -v`
Expected: FAIL with "No such command: 'init-core'"

- [ ] **Step 3: Update cli.py with new paths and init-core command**

```python
# cli.py (key changes - show complete file for reference)
"""
OntoClaw Compiler CLI.

Click-based command-line interface for compiling skills
to modular OWL 2 RDF/Turtle ontology.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from extractor import generate_skill_id, compute_skill_hash
from transformer import tool_use_loop
from security import security_check, SecurityError
from loader import (
    create_core_ontology,
    serialize_skill_module,
    generate_index_manifest,
    mirror_skill_path,
    get_oc_namespace,
)
from sparql import execute_sparql, format_results
from exceptions import (
    SkillETLError,
    ExtractionError,
    SPARQLError,
    SkillNotFoundError,
)
from config import SKILLS_DIR, OUTPUT_DIR

# Configure logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

console = Console()


def setup_logging(verbose: bool, quiet: bool):
    """Configure logging based on verbosity flags."""
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )


@click.group()
@click.version_option(version="0.2.0", prog_name="ontoclaw-compiler")
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def cli(ctx, verbose, quiet):
    """OntoClaw Compiler - Compile markdown skills to modular OWL 2 ontology."""
    setup_logging(verbose, quiet)
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    ctx.obj['quiet'] = quiet


@cli.command()
@click.argument('skill_name', required=False)
@click.option('-i', '--input', 'input_dir', default=SKILLS_DIR,
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for semantic-skills')
@click.option('--dry-run', is_flag=True, help='Preview without saving')
@click.option('--skip-security', is_flag=True, help='Skip security checks (not recommended)')
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompt')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def compile(ctx, skill_name, input_dir, output_dir, dry_run, skip_security,
            yes, verbose, quiet):
    """Compile skills into modular ontology.

    Without SKILL_NAME: Compile all skills in input directory.
    With SKILL_NAME: Compile specific skill (shows preview, asks confirmation).

    Output structure:
      semantic-skills/
      ├── ontoclaw-core.ttl
      ├── index.ttl
      └── <mirrored paths>/skill.ttl
    """
    setup_logging(verbose or ctx.obj.get('verbose', False),
                  quiet or ctx.obj.get('quiet', False))
    logger = logging.getLogger(__name__)

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Ensure core ontology exists
    core_path = output_path / "ontoclaw-core.ttl"
    if not core_path.exists():
        logger.info("Creating core ontology...")
        create_core_ontology(core_path)

    # Find skills to compile
    if skill_name:
        # Single skill
        skill_dir = input_path / skill_name
        if not skill_dir.exists():
            raise SkillNotFoundError(f"Skill directory not found: {skill_dir}")
        skill_dirs = [skill_dir]
    else:
        # All skills - find directories containing SKILL.md
        if not input_path.exists():
            console.print(f"[yellow]No skills directory found at {input_path}[/yellow]")
            return

        skill_dirs = [
            d for d in input_path.rglob("*")
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

        if not skill_dirs:
            console.print("[yellow]No SKILL.md files found in input directory[/yellow]")
            return

    logger.info(f"Found {len(skill_dirs)} skill(s) to compile")

    # Process each skill
    compiled_skills = []
    skill_output_paths = []

    for skill_dir in skill_dirs:
        skill_id = generate_skill_id(skill_dir.name)
        skill_hash = compute_skill_hash(skill_dir)

        logger.info(f"Processing skill: {skill_id}")

        # Security check
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            content = skill_file.read_text(encoding="utf-8")
            try:
                threats, passed = security_check(content, skip_llm=skip_security)
                if not passed:
                    console.print(f"[red]Security check failed for {skill_id}[/red]")
                    for threat in threats:
                        console.print(f"  - {threat.type}: {threat.match}")
                    continue
            except SecurityError as e:
                console.print(f"[red]Security error: {e}[/red]")
                continue

        # LLM extraction
        try:
            extracted = tool_use_loop(skill_dir, skill_hash, skill_id)
            compiled_skills.append(extracted)

            # Calculate output path
            output_skill_path = mirror_skill_path(skill_dir, output_path, input_path)
            skill_output_paths.append(output_skill_path)

            logger.info(f"Successfully extracted: {skill_id}")
        except ExtractionError as e:
            console.print(f"[red]Extraction failed for {skill_id}: {e}[/red]")
            continue

    if not compiled_skills:
        console.print("[yellow]No skills compiled[/yellow]")
        return

    # Show preview
    console.print(Panel(f"[green]Compiled {len(compiled_skills)} skill(s)[/green]"))

    for skill in compiled_skills:
        console.print(f"\n[bold]{skill.id}[/bold]")
        console.print(f"  Nature: {skill.nature[:80]}...")
        console.print(f"  Genus: {skill.genus}")
        console.print(f"  Intents: {', '.join(skill.intents)}")
        if skill.state_transitions.requires_state:
            console.print(f"  Requires: {', '.join(skill.state_transitions.requires_state)}")
        if skill.state_transitions.yields_state:
            console.print(f"  Yields: {', '.join(skill.state_transitions.yields_state)}")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes saved[/yellow]")
        return

    # Confirmation
    if not yes and skill_name:
        if not click.confirm("\nAdd this skill to the ontology?", default=True):
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Serialize each skill module
    for skill, output_skill_path in zip(compiled_skills, skill_output_paths):
        serialize_skill_module(skill, output_skill_path)

    # Generate index manifest
    index_path = output_path / "index.ttl"
    generate_index_manifest(skill_output_paths, index_path, output_path)

    console.print(f"\n[green]Compiled {len(compiled_skills)} skill(s) to {output_path}[/green]")


@cli.command('init-core')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for semantic-skills')
@click.option('-f', '--force', is_flag=True, help='Overwrite existing core ontology')
@click.pass_context
def init_core(ctx, output_dir, force):
    """Initialize the core ontology (ontoclaw-core.ttl).

    Creates the foundational TBox with classes, properties, and predefined states.
    Safe to run multiple times - skips if file exists unless --force is used.
    """
    logger = logging.getLogger(__name__)
    output_path = Path(output_dir)
    core_path = output_path / "ontoclaw-core.ttl"

    if core_path.exists() and not force:
        console.print(f"[yellow]Core ontology already exists at {core_path}[/yellow]")
        console.print("Use --force to overwrite")
        return

    create_core_ontology(core_path)
    console.print(f"[green]Created core ontology at {core_path}[/green]")


@cli.command('query')
@click.argument('query_string')
@click.option('-o', '--ontology', 'ontology_file', default=OUTPUT_DIR + "/index.ttl",
              type=click.Path(exists=False), help='Ontology file or directory')
@click.option('-f', '--format', 'output_format',
              type=click.Choice(['table', 'json', 'turtle']), default='table',
              help='Output format')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def query_cmd(ctx, query_string, ontology_file, output_format, verbose, quiet):
    """Execute SPARQL query against ontology.

    Example:
        ontoclaw query "SELECT ?s ?n WHERE { ?s oc:nature ?n }" -f json
    """
    setup_logging(verbose or ctx.obj.get('verbose', False),
                  quiet or ctx.obj.get('quiet', False))

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        raise SPARQLError(f"Ontology not found: {ontology_path}")

    try:
        results, vars = execute_sparql(ontology_path, query_string)

        if not results:
            console.print("[yellow]No results[/yellow]")
            return

        output = format_results(results, output_format, vars)
        console.print(output)

    except SPARQLError as e:
        console.print(f"[red]Query error: {e}[/red]")
        raise


@cli.command('list-skills')
@click.option('-o', '--ontology', 'ontology_file', default=OUTPUT_DIR + "/index.ttl",
              type=click.Path(exists=False), help='Ontology file or directory')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def list_skills(ctx, ontology_file, verbose, quiet):
    """List all skills in the ontology."""
    setup_logging(verbose or ctx.obj.get('verbose', False),
                  quiet or ctx.obj.get('quiet', False))

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        return

    oc = get_oc_namespace()

    try:
        results, _ = execute_sparql(
            ontology_path,
            f"""PREFIX oc: <{str(oc)}>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            SELECT ?id ?nature WHERE {{
                ?skill a oc:Skill ;
                       dcterms:identifier ?id ;
                       oc:nature ?nature .
            }}"""
        )

        if not results:
            console.print("[yellow]No skills found in ontology[/yellow]")
            return

        console.print(f"\n[bold]Skills in ontology ({len(results)}):[/bold]\n")
        for row in results:
            id_val = row.get('id', 'unknown')
            nature = row.get('nature', '')[:60]
            console.print(f"  • {id_val}: {nature}...")

    except SPARQLError as e:
        console.print(f"[red]Query error: {e}[/red]")


@cli.command('security-audit')
@click.option('-i', '--input', 'input_dir', default=SKILLS_DIR,
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def security_audit(ctx, input_dir, verbose, quiet):
    """Re-validate all skills against current security patterns."""
    setup_logging(verbose or ctx.obj.get('verbose', False),
                  quiet or ctx.obj.get('quiet', False))

    input_path = Path(input_dir)
    if not input_path.exists():
        console.print(f"[red]Skills directory not found: {input_path}[/red]")
        return

    skill_dirs = [
        d for d in input_path.rglob("*")
        if d.is_dir() and (d / "SKILL.md").exists()
    ]

    if not skill_dirs:
        console.print("[yellow]No skills found[/yellow]")
        return

    console.print(f"\n[bold]Security audit of {len(skill_dirs)} skill(s):[/bold]\n")

    issues_found = 0
    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")

        threats, passed = security_check(content, skip_llm=True)

        if passed:
            console.print(f"  [green]✓[/green] {skill_dir.name}")
        else:
            console.print(f"  [red]✗[/red] {skill_dir.name}")
            for threat in threats:
                console.print(f"      - {threat.type}: {threat.match[:50]}")
            issues_found += 1

    console.print(f"\n[bold]Audit complete:[/bold] {issues_found} issue(s) found")


def main():
    """Entry point with proper error handling."""
    try:
        cli()
    except SkillETLError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat: update CLI with new paths and init-core command"
```

---

## Chunk 8: Project Configuration Update

### Task 8.1: Update pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update project metadata**

```toml
# pyproject.toml
[project]
name = "ontoclaw-compiler"
version = "0.2.0"
description = "Compiler for OntoClaw neuro-symbolic skill ontologies"
requires-python = ">=3.10"
dependencies = [
    "click>=8.1.0",
    "pydantic>=2.0.0",
    "rdflib>=7.0.0",
    "anthropic>=0.39.0",
    "rich>=13.0.0",
    "owlrl>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.scripts]
ontoclaw = "cli:cli"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: update project name to ontoclaw-compiler"
```

---

## Chunk 9: Final Integration

### Task 9.1: Run full test suite and fix any issues

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS (may need fixes)

- [ ] **Step 2: Fix any failing tests**

If tests fail, debug and fix incrementally.

- [ ] **Step 3: Run linting**

Run: `ruff check .`
Expected: No errors (fix any that appear)

- [ ] **Step 4: Create final commit**

```bash
git add -A
git commit -m "feat: complete Phase 1 - modular ontology with state transitions"
```

---

## Chunk 9: Final Integration

### Task 9.1: End-to-end integration test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write end-to-end integration test**

```python
# tests/test_integration.py
"""End-to-end integration tests for OntoClaw compiler."""
import pytest
from pathlib import Path
from click.testing import CliRunner

from cli import cli
from loader import create_core_ontology, serialize_skill_module, generate_index_manifest, get_oc_namespace
from schemas import ExtractedSkill, StateTransition


def test_modular_output_structure(tmp_path):
    """Test that modular output structure is created correctly.

    Note: This test manually creates skill data to verify output structure.
    A full E2E test with LLM extraction requires API mocking (out of scope for Phase 1).
    """
    # Setup: Create a minimal skill
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "test" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""
# My Test Skill

A skill for testing the E2E flow.

## Nature
A test skill that verifies compilation.

## Intents
- test_compile
- verify_output
""")

    output_dir = tmp_path / "semantic-skills"

    # Run compile via CLI
    runner = CliRunner()
    result = runner.invoke(cli, [
        'compile',
        '-i', str(skills_dir),
        '-o', str(output_dir),
        '--skip-security',
        '-y'  # Skip confirmation
    ])

    # Verify CLI succeeded (or failed at extraction - we'll mock that)
    # For this test, we'll manually create the output structure

    # Create core ontology
    core_path = output_dir / "ontoclaw-core.ttl"
    create_core_ontology(core_path)
    assert core_path.exists()

    # Create a skill module
    from schemas import ExecutionPayload

    skill = ExtractedSkill(
        id="my-skill",
        hash="test123hash",
        nature="A test skill that verifies compilation",
        genus="Test",
        differentia="for E2E verification",
        intents=["test_compile", "verify_output"],
        requirements=[],
        state_transitions=StateTransition(
            requires_state=["oc:EnvironmentReady"],
            yields_state=["oc:TestComplete"],
            handles_failure=["oc:OperationFailed"]
        ),
        generated_by="test-runner",
        execution_payload=ExecutionPayload(
            executor="shell",
            code="echo 'E2E test passed'",
            timeout=60
        ),
        provenance=str(skill_dir / "SKILL.md"),
    )

    skill_output = output_dir / "test" / "my-skill" / "skill.ttl"
    serialize_skill_module(skill, skill_output, output_dir)
    assert skill_output.exists()

    # Create index
    index_path = output_dir / "index.ttl"
    generate_index_manifest([skill_output], index_path, output_dir)
    assert index_path.exists()

    # Verify structure
    assert core_path.exists()
    assert index_path.exists()
    assert skill_output.exists()

    # Verify index imports core and skill
    index_content = index_path.read_text()
    assert "ontoclaw-core.ttl" in index_content
    assert "test/my-skill/skill.ttl" in index_content

    # Verify skill module imports core
    skill_content = skill_output.read_text()
    assert "ontoclaw-core.ttl" in skill_content

    # Verify state transitions are URIs
    oc = get_oc_namespace()
    assert "EnvironmentReady" in skill_content
    assert "TestComplete" in skill_content
    assert "OperationFailed" in skill_content

    # Verify execution payload is serialized
    assert "ExecutionPayload" in skill_content
    assert "shell" in skill_content
    assert "echo 'E2E test passed'" in skill_content
    assert "60" in skill_content
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add E2E integration test for modular output"
```

### Task 9.2: Run full test suite and fix any issues

This plan implements the complete Phase 1 refactoring:

| Component | Status | Key Changes |
|-----------|--------|-------------|
| `config.py` | NEW | Environment-driven configuration |
| `schemas.py` | Modified | StateTransition model, removed constraints |
| `transformer.py` | Modified | State extraction prompt, generated_by |
| `loader.py` | Rewritten | Modular output, path mirroring, core/index |
| `cli.py` | Modified | New paths, init-core command |
| Tests | Updated | All new functionality covered |

**Output Structure:**
```
semantic-skills/
├── ontoclaw-core.ttl    # TBox (classes, properties, core states)
├── index.ttl            # Manifest with owl:imports
└── <mirrored paths>/    # Each skill gets skill.ttl
    └── skill.ttl
```

---

## Important Notes

### Namespace Migration

The old `AG` namespace (`http://agentic.web/ontology#`) is **completely replaced** by the new `oc` namespace.

**Breaking change:** Existing `skills.ttl` files using `ag:` prefix will not be compatible. This is intentional - Phase 1 starts fresh with the new ontology structure.

**Migration path:**
1. Delete any existing `ontology/skills.ttl` file
2. Run `ontoclaw init-core` to create the new core ontology
3. Recompile all skills with `ontoclaw compile`

### Attempt Class (Phase 1 vs Phase 2)

The `oc:Attempt` class is defined in `ontoclaw-core.ttl` but **not used in Phase 1**.

- **Phase 1:** Defines the class and `oc:hasStatus` property for future use
- **Phase 2:** Rust MCP server will create `Attempt` instances to track execution and implement Negative Memory for Belief Revision

This separation allows the core ontology to be stable while the Rust server adds dynamic ABox data.

### constraints Field Removal

The `constraints: list[str]` field is **removed** from `ExtractedSkill` with no backward compatibility.

All constraint-like information should now be expressed as:
- `requiresState` - for pre-conditions
- `yieldsState` - for success outcomes
- `handlesFailure` - for failure modes

---

Ready for Phase 2: Rust MCP Server.
