import json
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
        """Validate that all state URIs match the pattern oc:[A-Z][a-zA-Z0-9]*"""
        import re
        pattern = r'^oc:[A-Z][a-zA-Z0-9]*$'
        for uri in v:
            if not re.match(pattern, uri):
                raise ValueError(
                    f"Invalid state URI '{uri}'. Must match pattern {pattern}"
                )
        return v


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

    @model_validator(mode='before')
    @classmethod
    def parse_nested_json(cls, data: Any) -> Any:
        """Parse JSON strings for nested models if LLM returns them as strings."""
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

        return data

    @computed_field
    @property
    def skill_type(self) -> Literal["executable", "declarative"]:
        """Derive skill type from presence of execution_payload."""
        return "executable" if self.execution_payload is not None else "declarative"
