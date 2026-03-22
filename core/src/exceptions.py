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


class OrphanSubSkillsError(SkillETLError):
    """Raised when auxiliary .md files exist without a parent SKILL.md."""
    exit_code = 10

    def __init__(self, directory: str, orphan_files: list[str]):
        self.directory = directory
        self.orphan_files = orphan_files
        message = f"Directory '{directory}' has auxiliary .md files {orphan_files} but no SKILL.md. Sub-skills cannot exist without parent."
        super().__init__(message)
