"""
SHACL Validation Module.

Validates skill RDF graphs against the OntoClaw constitutional SHACL shapes.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from rdflib import Graph

logger = logging.getLogger(__name__)

# Path to SHACL shapes file (project root / specs /)
SHACL_SHAPES_PATH = Path(__file__).parent.parent / "specs" / "ontoclaw.shacl.ttl"


class ValidationResult(NamedTuple):
    """Result of SHACL validation."""
    conforms: bool
    results_text: str
    results_graph: Graph | None
