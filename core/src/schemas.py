import json
import re
import warnings
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator, computed_field
from typing import Literal, Any


class Requirement(BaseModel):
    type: Literal["EnvVar", "Tool", "Hardware", "API", "Knowledge"]
    value: str
    optional: bool = False


class ExecutionPayload(BaseModel):
    executor: Literal["shell", "python", "node", "claude_tool"]
    code: str
    timeout: int | None = None


class StateTransition(BaseModel):
    """Represents state transitions for skill execution.

    Uses structured state URIs that the Rust MCP server can reason about.
    All state URIs must match the pattern: oc:[A-Z][a-zA-Z0-9]*
    """
    requires_state: list[str] = Field(default_factory=list)  # URIs like ["oc:SystemAuthenticated"]
    yields_state: list[str] = Field(default_factory=list)    # URIs like ["oc:DocumentCreated"]
    handles_failure: list[str] = Field(default_factory=list) # URIs like ["oc:PermissionDenied"]

    @field_validator('requires_state', 'yields_state', 'handles_failure')
    @classmethod
    def validate_state_uris(cls, v: list[str]) -> list[str]:
        """Validate that all state URIs match the pattern oc:[A-Z][a-zA-Z0-9]*(?::[a-zA-Z0-9_-]+)?"""
        import re
        # Pattern allows: oc:StateName or oc:StateName:parameter
        pattern = r'^oc:[A-Z][a-zA-Z0-9]*(?::[a-zA-Z0-9_-]+)?$'
        for uri in v:
            if not re.match(pattern, uri):
                raise ValueError(
                    f"Invalid state URI '{uri}'. Must match pattern oc:StateName or oc:StateName:parameter"
                )
        return v


class SeverityLevel(str, Enum):
    """Severity levels for knowledge nodes."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# 26 concrete knowledge node types across 10 dimensions
KnowledgeNodeType = Literal[
    # Dimension 1: NormativeRule
    "Standard", "AntiPattern", "Constraint",
    # Dimension 2: StrategicInsight
    "Heuristic", "DesignPrinciple", "WorkflowStrategy",
    # Dimension 3: ResilienceTactic
    "KnownIssue", "RecoveryTactic",
    # Dimension 4: ExecutionPhysics
    "Idempotency", "SideEffect", "PerformanceProfile",
    # Dimension 5: Observability
    "SuccessIndicator", "TelemetryPattern",
    # Dimension 6: SecurityGuardrail
    "SecurityImplication", "DestructivePotential", "FallbackStrategy",
    # Dimension 7: CognitiveBoundary
    "RequiresHumanClarification", "AssumptionBoundary", "AmbiguityTolerance",
    # Dimension 8: ResourceProfile
    "TokenEconomy", "ComputeCost",
    # Dimension 9: TrustMetric
    "ExecutionDeterminism", "DataProvenance",
    # Dimension 10: LifecycleHook
    "PreFlightCheck", "PostFlightValidation", "RollbackProcedure",
]


class KnowledgeNode(BaseModel):
    """Epistemic knowledge node extracted from a skill.

    Each node captures a single piece of cognitive/physical/temporal
    knowledge that the skill imparts to the agent.
    """
    node_type: KnowledgeNodeType
    directive_content: str  # The actual rule/guideline
    applies_to_context: str  # When this rule applies
    has_rationale: str       # Why this rule exists
    severity_level: SeverityLevel | None = None  # Optional priority


class ExtractedSkill(BaseModel):
    id: str
    hash: str
    nature: str
    genus: str
    differentia: str
    intents: list[str]
    requirements: list[Requirement] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    extends: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    state_transitions: StateTransition | None = None
    generated_by: str = "unknown"
    execution_payload: ExecutionPayload | None = None
    provenance: str | None = None
    knowledge_nodes: list[KnowledgeNode] = Field(default_factory=list)

    # New metadata fields (OntoCore refactoring)
    category: str | None = None
    version: str | None = None
    license: str | None = None
    author: str | None = None
    package_name: str | None = None
    is_user_invocable: bool = True
    argument_hint: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)

    @field_validator('depends_on', 'extends', 'contradicts')
    @classmethod
    def validate_skill_relation_ids(cls, values: list[str]) -> list[str]:
        """Validate and normalize relation targets.

        Accepts: bare skill ids ("office"), qualified ("author/package/skill"),
        or URIs. All non-URI references are normalized to the bare skill ID
        (last segment), which is what the serialization layer expects for
        building correct oc:skill_ URIs.
        """
        import re

        pattern = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
        normalized = []
        for value in values:
            candidate = value.strip()
            if not candidate:
                raise ValueError("Skill relation identifiers cannot be empty")
            if candidate.startswith(("http://", "https://", "oc:")):
                normalized.append(candidate)
                continue
            parts = candidate.split('/')
            # Validate all segments look like valid identifiers
            for part in parts:
                if not pattern.match(part):
                    raise ValueError(
                        f"Invalid skill relation '{value}'. Use canonical skill ids like 'office' or 'docx-review'."
                    )
            # Always normalize to bare skill ID (last segment)
            normalized.append(parts[-1])
        return normalized

    @field_validator('is_user_invocable', mode='before')
    @classmethod
    def coerce_is_user_invocable(cls, v: Any) -> bool:
        """Coerce string values to boolean for TTL serialization correctness."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('true', 'yes', '1')
        return bool(v)

    @model_validator(mode='before')
    @classmethod
    def parse_and_clean_nested_data(cls, data: Any) -> Any:
        """Parse JSON strings and filter incomplete knowledge_nodes."""
        if isinstance(data, dict):
            # Parse state_transitions if it's a string
            if 'state_transitions' in data and isinstance(data['state_transitions'], str):
                try:
                    data['state_transitions'] = json.loads(data['state_transitions'])
                except json.JSONDecodeError:
                    pass

            # Parse execution_payload if it's a string
            if 'execution_payload' in data and isinstance(data['execution_payload'], str):
                try:
                    data['execution_payload'] = json.loads(data['execution_payload'])
                except json.JSONDecodeError:
                    pass

            # Filter out incomplete knowledge_nodes (LLM sometimes returns partial nodes)
            # - Keep already constructed KnowledgeNode objects
            # - Parse string elements as JSON, then validate as dicts
            # - For dicts, require all fields with non-empty values
            # - Emit warning via warnings.warn() when discarding incomplete/invalid nodes
            if 'knowledge_nodes' in data and isinstance(data['knowledge_nodes'], list):
                required_fields = {'node_type', 'directive_content', 'applies_to_context', 'has_rationale'}
                filtered_nodes = []
                for i, node in enumerate(data['knowledge_nodes']):
                    if isinstance(node, KnowledgeNode):
                        # Already a valid KnowledgeNode object, keep it
                        filtered_nodes.append(node)
                    elif isinstance(node, str):
                        # Try to parse string as JSON
                        try:
                            parsed = json.loads(node)
                            if isinstance(parsed, dict):
                                if required_fields.issubset(parsed.keys()) and all(parsed.get(f) for f in required_fields):
                                    filtered_nodes.append(parsed)
                                else:
                                    warnings.warn(
                                        f"Knowledge node at index {i} (parsed from string) is incomplete, discarding. "
                                        f"Missing or empty fields: {required_fields - set(k for k in required_fields if parsed.get(k))}"
                                    )
                            else:
                                warnings.warn(
                                    f"Knowledge node at index {i} (parsed from string) is not a dict, discarding. Got: {type(parsed).__name__}"
                                )
                        except json.JSONDecodeError:
                            warnings.warn(
                                f"Knowledge node at index {i} is not valid JSON, discarding. Length: {len(node)} characters."
                            )
                    elif isinstance(node, dict):
                        # Check if dict has all required fields with non-empty values
                        if required_fields.issubset(node.keys()) and all(node.get(f) for f in required_fields):
                            filtered_nodes.append(node)
                        else:
                            warnings.warn(
                                f"Knowledge node at index {i} is incomplete, discarding. "
                                f"Missing or empty fields: {required_fields - set(k for k in required_fields if node.get(k))}"
                            )
                    # Skip other types (not KnowledgeNode, str, or dict)
                    else:
                        warnings.warn(
                            f"Knowledge node at index {i} has unsupported type {type(node).__name__}, discarding."
                        )
                data['knowledge_nodes'] = filtered_nodes

        return data

    @computed_field
    @property
    def skill_type(self) -> Literal["executable", "declarative"]:
        """Derive skill type from presence of execution_payload."""
        return "executable" if self.execution_payload is not None else "declarative"


# =============================================================================
# Phase 1 Models (Python-only, no LLM)
# =============================================================================

class Frontmatter(BaseModel):
    """YAML frontmatter extracted via Python parser.

    Validates Anthropic skill authoring requirements:
    - name: max 64 chars, lowercase, hyphens only, no reserved words
    - description: max 1024 chars, no XML tags
    """
    name: str
    description: str
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        # Convert scope prefix separator (e.g., "ckm:banner-design" → "ckm-banner-design")
        if ':' in v:
            v = v.replace(':', '-', 1)

        # Auto-normalize: lowercase, spaces/underscores → hyphens, collapse repeated hyphens
        normalized = v.lower().strip()
        normalized = re.sub(r'[\s_]+', '-', normalized)
        normalized = re.sub(r'[^a-z0-9-]', '-', normalized)
        normalized = re.sub(r'-+', '-', normalized)
        normalized = normalized.strip('-')

        if not normalized:
            raise ValueError("Skill name is empty after normalization")
        if len(normalized) > 64:
            raise ValueError(f"Skill name exceeds 64 characters: {len(normalized)}")

        # Block only if the FULL name is a reserved word (not a compound like "system-design")
        fully_reserved = ('ontoskills', 'index')
        if normalized in fully_reserved:
            raise ValueError(f"Skill name '{normalized}' is a reserved identifier")

        return normalized

    @field_validator('description')
    @classmethod
    def validate_description(cls, v: str) -> str:
        if len(v) > 1024:
            raise ValueError(f"Description exceeds 1024 characters: {len(v)}")
        if re.search(r'<[a-zA-Z][^>]*>', v):
            raise ValueError("Description contains XML/HTML tags (not allowed)")
        return v


class FileInfo(BaseModel):
    """File metadata computed via Python, not LLM."""
    relative_path: str
    content_hash: str
    file_size: int
    mime_type: str


class DirectoryScan(BaseModel):
    """Phase 1 output - all filesystem metadata."""
    frontmatter: Frontmatter
    skill_id: str
    qualified_id: str
    content_hash: str
    provenance_path: str
    files: list[FileInfo]
    skill_md_content: str
    file_tree: str  # Formatted string for LLM context


# =============================================================================
# Phase 2 Models (LLM Extraction)
# =============================================================================

class ReferenceFile(BaseModel):
    """Reference file identified by LLM for progressive disclosure."""
    relative_path: str
    purpose: Literal["api-reference", "examples", "guide", "domain-specific", "other"]


class ExecutableScript(BaseModel):
    """Executable script identified by LLM."""
    relative_path: str
    executor: Literal["python", "bash", "node", "other"]
    execution_intent: Literal["execute", "read_only"] = "execute"
    command_template: str | None = None
    requirements: list[str] = Field(default_factory=list)  # Plain tool names: ["pypdf", "pdfplumber"]
    produces_output: str | None = None


class Example(BaseModel):
    """Input/output example pair for pattern matching."""
    name: str
    input_description: str
    output_example: str
    tags: list[str] = Field(default_factory=list)


class WorkflowStep(BaseModel):
    """Single workflow step."""
    step_id: str
    description: str
    expected_outcome: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class Workflow(BaseModel):
    """Sequential workflow with dependencies."""
    workflow_id: str
    name: str
    description: str
    steps: list[WorkflowStep]


# =============================================================================
# Merged Model (Phase 1 + Phase 2)
# =============================================================================

class CompiledSkill(ExtractedSkill):
    """Final compiler output - extends ExtractedSkill with new fields.

    Includes:
    - Phase 1 data: frontmatter, files (from loader.py)
    - Phase 2 data: reference_files, executable_scripts, examples, workflows
    """
    # From Phase 1
    frontmatter: Frontmatter | None = None
    files: list[FileInfo] = Field(default_factory=list)

    # From Phase 2
    reference_files: list[ReferenceFile] = Field(default_factory=list)
    executable_scripts: list[ExecutableScript] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    workflows: list[Workflow] = Field(default_factory=list)
