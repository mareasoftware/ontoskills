import pytest
from compiler.exceptions import SkillETLError, SecurityError


def test_exceptions_exit_codes():
    assert SkillETLError.exit_code == 1
    assert SecurityError.exit_code == 3


def test_ontology_validation_error_exists():
    """Test that OntologyValidationError exception exists."""
    from compiler.exceptions import OntologyValidationError, SkillETLError

    # Should be subclass of SkillETLError
    assert issubclass(OntologyValidationError, SkillETLError)

    # Should have exit_code 8
    assert OntologyValidationError.exit_code == 8

    # Should be instantiable with message
    e = OntologyValidationError("SHACL validation failed")
    assert "SHACL" in str(e)
