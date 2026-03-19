class SkillETLError(Exception):
    exit_code: int = 1


class OntologyLoadError(SkillETLError):
    exit_code = 5


class SecurityError(SkillETLError):
    exit_code = 3


class ExtractionError(SkillETLError):
    exit_code = 4


class SPARQLError(SkillETLError):
    exit_code = 6


class SkillNotFoundError(SkillETLError):
    exit_code = 7


class OntologyValidationError(SkillETLError):
    """Raised when skill ontology fails SHACL validation."""
    exit_code = 8


class DriftDetectedError(SkillETLError):
    """Raised when breaking semantic drift is detected in the ontology."""
    exit_code = 9
