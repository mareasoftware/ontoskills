import json
from enum import Enum
from pydantic import BaseModel, field_validator, model_validator, computed_field
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
    requires_state: list[str] = []  # URIs like ["oc:SystemAuthenticated"]
    yields_state: list[str] = []    # URIs like ["oc:DocumentCreated"]
    handles_failure: list[str] = [] # URIs like ["oc:PermissionDenied"]

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


# 30 concrete knowledge node types across 10 dimensions
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
    requirements: list[Requirement]
    depends_on: list[str] = []
    extends: list[str] = []
    contradicts: list[str] = []
    state_transitions: StateTransition | None = None
    generated_by: str = "unknown"
    execution_payload: ExecutionPayload | None = None
    provenance: str | None = None
    knowledge_nodes: list[KnowledgeNode] = []

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
            # Only filter when nodes are dicts; leave KnowledgeNode objects as-is
            if 'knowledge_nodes' in data and isinstance(data['knowledge_nodes'], list):
                required_fields = {'node_type', 'directive_content', 'applies_to_context', 'has_rationale'}
                filtered_nodes = []
                for node in data['knowledge_nodes']:
                    if isinstance(node, KnowledgeNode):
                        # Already a valid KnowledgeNode object, keep it
                        filtered_nodes.append(node)
                    elif isinstance(node, dict):
                        # Check if dict has all required fields with non-empty values
                        if required_fields.issubset(node.keys()) and all(node.get(f) for f in required_fields):
                            filtered_nodes.append(node)
                    # Skip invalid/incomplete nodes
                data['knowledge_nodes'] = filtered_nodes

        return data

    @computed_field
    @property
    def skill_type(self) -> Literal["executable", "declarative"]:
        """Derive skill type from presence of execution_payload."""
        return "executable" if self.execution_payload is not None else "declarative"
