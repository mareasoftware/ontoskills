"""
SHACL Validation Module.

Validates skill RDF graphs against the OntoClaw constitutional SHACL shapes.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from rdflib import Graph

from compiler.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

# Path to SHACL shapes file (project root / specs /)
SHACL_SHAPES_PATH = Path(__file__).parent.parent / "specs" / "ontoclaw.shacl.ttl"

# Path to core ontology (output directory)
CORE_ONTOLOGY_PATH = Path(OUTPUT_DIR) / "ontoclaw-core.ttl"


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
