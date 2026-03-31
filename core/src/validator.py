"""
SHACL Validation Module.

Validates skill RDF graphs against the OntoSkills constitutional SHACL shapes.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from rdflib import Graph
from pyshacl import validate

from compiler.config import CORE_ONTOLOGY_FILENAME, OUTPUT_DIR
from compiler.exceptions import OntologyValidationError

logger = logging.getLogger(__name__)

# Path to SHACL shapes file (core/specs/)
SHACL_SHAPES_PATH = Path(__file__).parent.parent / "specs" / "ontoskills.shacl.ttl"

# Path to core ontology (output directory)
CORE_ONTOLOGY_PATH = Path(OUTPUT_DIR) / CORE_ONTOLOGY_FILENAME


class ValidationResult(NamedTuple):
    """Result of SHACL validation."""
    conforms: bool
    results_text: str
    results_graph: Graph | None


def load_shacl_shapes() -> Graph:
    """Load the SHACL shapes graph from disk."""
    if not SHACL_SHAPES_PATH.exists():
        raise FileNotFoundError(f"SHACL shapes file not found: {SHACL_SHAPES_PATH}")

    shapes_graph = Graph()
    shapes_graph.parse(SHACL_SHAPES_PATH, format="turtle")
    logger.debug(f"Loaded SHACL shapes from {SHACL_SHAPES_PATH}")
    return shapes_graph


def load_core_ontology() -> Graph | None:
    """
    Load the core ontology (TBox) for class definitions.

    CRITICAL: This is needed for sh:class validation to work correctly.
    Without the core ontology, pySHACL doesn't know that oc:SystemAuthenticated
    is an oc:State, causing false negatives in state validation.
    """
    if not CORE_ONTOLOGY_PATH.exists():
        logger.warning(f"Core ontology not found at {CORE_ONTOLOGY_PATH}, state validation may fail")
        return None

    ont_graph = Graph()
    ont_graph.parse(CORE_ONTOLOGY_PATH, format="turtle")
    logger.debug(f"Loaded core ontology from {CORE_ONTOLOGY_PATH}")
    return ont_graph


def validate_skill_graph(skill_graph: Graph, shapes_graph: Graph | None = None) -> ValidationResult:
    """
    Validate a skill RDF graph against SHACL shapes.

    Args:
        skill_graph: RDF graph containing the skill to validate
        shapes_graph: SHACL shapes graph (default: load from specs/)

    Returns:
        ValidationResult with conforms flag and detailed report
    """
    if shapes_graph is None:
        shapes_graph = load_shacl_shapes()

    # Load core ontology for class definitions (essential for sh:class validation)
    ont_graph = load_core_ontology()

    # Run SHACL validation
    # NOTE: We use inference='none' because pySHACL has a bug where it treats
    # Literal values in the data graph as focus nodes when using RDFS inference.
    # The ont_graph is still passed for sh:class validation to work.
    conforms, results_graph, results_text = validate(
        skill_graph,
        shacl_graph=shapes_graph,
        ont_graph=ont_graph,  # PASS CORE ONTOLOGY! Required for sh:class oc:State
        inference='none',  # Don't use RDFS inference (causes Literal validation bug)
        abort_on_first=False,  # Collect all violations
        allow_warnings=True,
        meta_shacl=False,
        debug=False
    )

    logger.info(f"SHACL validation: conforms={conforms}")

    return ValidationResult(
        conforms=conforms,
        results_text=results_text,
        results_graph=results_graph
    )


def validate_and_raise(skill_graph: Graph, shapes_graph: Graph | None = None) -> None:
    """
    Validate a skill graph and raise exception if invalid.

    Args:
        skill_graph: RDF graph to validate
        shapes_graph: SHACL shapes graph (default: load from specs/)

    Raises:
        OntologyValidationError: If validation fails
    """
    result = validate_skill_graph(skill_graph, shapes_graph)

    if not result.conforms:
        logger.error(f"Skill validation failed:\n{result.results_text}")
        raise OntologyValidationError(
            result.results_text,
            result.results_graph
        )

    logger.debug("Skill passed SHACL validation")
