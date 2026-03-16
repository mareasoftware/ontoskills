from pydantic import BaseModel, field_validator
from typing import Literal


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
    execution_payload: ExecutionPayload | None
    provenance: str | None
