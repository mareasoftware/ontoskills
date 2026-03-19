"""
Storage Module.

Handles file I/O operations for skills and ontologies including:
- Path mirroring operations
- File loading
- Merging skills into ontologies
- Atomic saves with backup
- Orphaned skill cleanup
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import owlrl
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef
from rdflib.namespace import DCTERMS, SKOS, PROV

from compiler.schemas import ExtractedSkill
from compiler.exceptions import OntologyLoadError, OntologyValidationError
from compiler.config import BASE_URI, SKILLS_DIR, OUTPUT_DIR, resolve_ontology_root
from compiler.core_ontology import get_oc_namespace
from compiler.serialization import serialize_skill
from compiler.validator import validate_and_raise

logger = logging.getLogger(__name__)


# =============================================================================
# Path Operations
# =============================================================================

def mirror_skill_path(skill_dir: Path, output_base: Path) -> Path:
    """
    Mirror the skills directory structure to the output directory.

    Mirroring rule:
        skills/{path}/SKILL.md → ontoskills/{path}/ontoskill.ttl

    Args:
        skill_dir: Path to skill directory (e.g., skills/xlsx/pdf/pptx)
        output_base: Base output directory (e.g., ontoskills/)

    Returns:
        Path to output ontoskill.ttl file (e.g., ontoskills/xlsx/pdf/pptx/ontoskill.ttl)
    """
    # Convert to absolute paths if needed
    skill_dir = skill_dir.resolve()
    output_base = output_base.resolve()

    # Get relative path from skills directory
    # If skill_dir is /path/to/skills/xlsx/pdf/pptx
    # and SKILLS_DIR is /path/to/skills
    # relative should be xlsx/pdf/pptx
    try:
        skills_base = Path(SKILLS_DIR).resolve()
        relative = skill_dir.relative_to(skills_base)
    except ValueError:
        # If skill_dir is not under SKILLS_DIR, try to extract relative path
        # Check if it looks like a path under a "skills" directory
        parts = skill_dir.parts
        if 'skills' in parts:
            # Extract path after 'skills' directory
            skills_idx = parts.index('skills')
            relative = Path(*parts[skills_idx + 1:])
        else:
            # Fall back to using the skill directory name
            relative = skill_dir.name

    # Mirror the path structure
    output_path = output_base / relative / "ontoskill.ttl"
    return output_path


def get_output_path(skill_dir: Path, output_base: Optional[Path] = None) -> Path:
    """
    Get the output path for a skill module.

    Args:
        skill_dir: Path to skill directory containing SKILL.md
        output_base: Base output directory (default: from config)

    Returns:
        Path where ontoskill.ttl should be written
    """
    if output_base is None:
        output_base = Path(OUTPUT_DIR).resolve()

    return mirror_skill_path(skill_dir, output_base)


def create_output_directory(skill_dir: Path, output_base: Optional[Path] = None) -> Path:
    """
    Create the output directory for a skill module.

    Args:
        skill_dir: Path to skill directory containing SKILL.md
        output_base: Base output directory (default: from config)

    Returns:
        Path to created output directory
    """
    output_path = get_output_path(skill_dir, output_base)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path.parent


# =============================================================================
# File Loading
# =============================================================================

def load_skill_module(module_path: Path) -> Graph:
    """
    Load a skill module from an ontoskill.ttl file.

    Args:
        module_path: Path to ontoskill.ttl file

    Returns:
        RDF Graph containing the skill module

    Raises:
        OntologyLoadError: If file cannot be loaded
    """
    if not module_path.exists():
        raise OntologyLoadError(f"Skill module not found: {module_path}")

    try:
        graph = Graph()
        graph.parse(module_path, format="turtle")
        logger.info(f"Loaded skill module from {module_path} with {len(graph)} triples")
        return graph
    except Exception as e:
        raise OntologyLoadError(f"Failed to load skill module: {e}")


def load_ontology(ontology_path: Path) -> Graph:
    """
    Load an existing ontology from file.

    Args:
        ontology_path: Path to skills.ttl file

    Returns:
        RDF Graph with loaded ontology

    Raises:
        OntologyLoadError: If file cannot be loaded
    """
    if not ontology_path.exists():
        logger.info(f"Creating new ontology at {ontology_path}")
        # Create a minimal graph with namespace bindings
        g = Graph()
        oc = get_oc_namespace()
        g.bind("oc", oc)
        g.bind("owl", OWL)
        g.bind("rdf", RDF)
        g.bind("rdfs", RDFS)
        g.bind("dcterms", DCTERMS)
        g.bind("skos", SKOS)
        g.bind("prov", PROV)
        return g

    try:
        graph = Graph()
        graph.parse(ontology_path, format="turtle")
        logger.info(f"Loaded ontology with {len(graph)} triples")
        return graph
    except Exception as e:
        raise OntologyLoadError(f"Failed to load ontology: {e}")


# =============================================================================
# Mapping Functions
# =============================================================================

def get_hash_mapping(graph: Graph) -> dict[str, URIRef]:
    """
    Extract hash → URI mapping from existing ontology.

    Args:
        graph: RDF graph to scan

    Returns:
        Dictionary mapping hashes to skill URIs
    """
    oc = get_oc_namespace()
    mapping = {}
    for skill_uri in graph.subjects(RDF.type, oc.Skill):
        hash_literal = graph.value(skill_uri, oc.contentHash)
        if hash_literal:
            mapping[str(hash_literal)] = skill_uri
    return mapping


def get_id_mapping(graph: Graph) -> dict[str, URIRef]:
    """
    Extract ID → URI mapping from existing ontology.

    Args:
        graph: RDF graph to scan

    Returns:
        Dictionary mapping IDs to skill URIs
    """
    oc = get_oc_namespace()
    mapping = {}
    for skill_uri in graph.subjects(RDF.type, oc.Skill):
        id_literal = graph.value(skill_uri, DCTERMS.identifier)
        if id_literal:
            mapping[str(id_literal)] = skill_uri
    return mapping


# =============================================================================
# Skill Removal
# =============================================================================

def remove_skill(graph: Graph, skill_uri: URIRef) -> None:
    """
    Remove all triples for a skill from the graph.

    Args:
        graph: RDF graph to modify
        skill_uri: URI of skill to remove
    """
    oc = get_oc_namespace()

    # Remove all triples where skill is subject
    for predicate in set(graph.predicates(subject=skill_uri)):
        for obj in graph.objects(skill_uri, predicate):
            graph.remove((skill_uri, predicate, obj))

    # Remove requirement blank nodes
    for req_uri in graph.objects(skill_uri, oc.hasRequirement):
        for p, o in list(graph.predicate_objects(req_uri)):
            graph.remove((req_uri, p, o))

    # Remove payload blank node
    payload_uri = graph.value(skill_uri, oc.hasPayload)
    if payload_uri:
        for p, o in list(graph.predicate_objects(payload_uri)):
            graph.remove((payload_uri, p, o))


# =============================================================================
# Skill Merging
# =============================================================================

def merge_skill(ontology_path: Path, skill: ExtractedSkill, force: bool = False) -> Graph:
    """
    Intelligently merge a skill into the ontology.

    - If hash exists → skip (unchanged), unless force=True
    - If same ID but different hash → remove old, add new
    - If new ID → add

    Args:
        ontology_path: Path to ontology file
        skill: Skill to merge
        force: If True, skip hash check and always merge

    Returns:
        Updated graph (not saved to disk)
    """
    graph = load_ontology(ontology_path)
    hash_mapping = get_hash_mapping(graph)
    id_mapping = get_id_mapping(graph)

    # Check if unchanged (same hash) - skip if not forcing
    if not force and skill.hash in hash_mapping:
        logger.info(f"Skill {skill.id} unchanged (hash match), skipping")
        return graph

    # Check if updated (same ID, different hash)
    if skill.id in id_mapping:
        old_uri = id_mapping[skill.id]
        logger.info(f"Skill {skill.id} updated, removing old version")
        remove_skill(graph, old_uri)

    # Add new/updated skill
    logger.info(f"Adding skill {skill.id} to ontology")
    serialize_skill(graph, skill)

    # VALIDATE BEFORE RETURNING
    try:
        validate_and_raise(graph)
    except OntologyValidationError as e:
        logger.critical(f"Skill {skill.id} failed validation, not merging")
        raise

    return graph


# =============================================================================
# Atomic Save with Backup
# =============================================================================

def save_ontology_atomic(
    ontology_path: Path,
    graph: Graph,
    backup_dir: Optional[Path] = None,
    max_backups: int = 5
) -> None:
    """
    Save ontology with atomic write and backup.

    1. Backup existing file
    2. Write to temp file
    3. Atomic rename
    4. Cleanup old backups

    Args:
        ontology_path: Path to skills.ttl
        graph: RDF graph to save
        backup_dir: Directory for backups (default: ontology_dir/backups/)
        max_backups: Maximum number of backups to keep
    """
    if backup_dir is None:
        backup_dir = ontology_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Backup existing file
    if ontology_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"skills_{timestamp}.ttl"
        shutil.copy2(ontology_path, backup_path)
        logger.info(f"Created backup: {backup_path}")

    # Write to temp file
    temp_path = ontology_path.with_suffix(".ttl.tmp")
    graph.serialize(temp_path, format="turtle")

    # Atomic rename
    shutil.move(str(temp_path), str(ontology_path))
    logger.info(f"Saved ontology to {ontology_path}")

    # Cleanup old backups
    backups = sorted(backup_dir.glob("skills_*.ttl"))
    while len(backups) > max_backups:
        oldest = backups.pop(0)
        oldest.unlink()
        logger.debug(f"Removed old backup: {oldest}")


# =============================================================================
# Reasoning
# =============================================================================

def apply_reasoning(graph: Graph) -> Graph:
    """
    Apply OWL 2 RL reasoning to infer new triples.

    Inferences:
    - Inverse: A dependsOn B → B enables A
    - Transitive: A extends B, B extends C → A extends C
    - Symmetric: A contradicts B → B contradicts A

    Args:
        graph: RDF graph to expand

    Returns:
        Same graph with inferred triples added
    """
    logger.info("Applying OWL reasoning...")
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(graph)
    logger.info(f"Reasoning complete, graph now has {len(graph)} triples")
    return graph


# =============================================================================
# Index Manifest Generation
# =============================================================================

def generate_index_manifest(
    skill_paths: list[Path],
    index_path: Path,
    output_base: Optional[Path] = None
) -> None:
    """
    Generate the index.ttl manifest that lists all skill modules.

    Creates an index manifest with owl:imports referencing all skill modules,
    enabling SPARQL queries against the combined ontology by loading index.ttl.

    Args:
        skill_paths: List of paths to ontoskill.ttl module files
        index_path: Path where index.ttl will be written
        output_base: Base output directory for computing relative paths
    """
    if output_base is None:
        output_base = Path(OUTPUT_DIR).resolve()
    else:
        output_base = output_base.resolve()
    ontology_root = resolve_ontology_root(output_base)

    oc = get_oc_namespace()
    g = Graph()

    # Bind namespaces
    g.bind("oc", oc)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)

    # Ontology header
    base_uri = URIRef(BASE_URI.rstrip('#'))
    g.add((base_uri, RDF.type, OWL.Ontology))
    g.add((base_uri, DCTERMS.title, Literal("OntoClaw Skill Index")))
    g.add((base_uri, DCTERMS.description, Literal(
        "Index manifest referencing all compiled skill modules"
    )))
    g.add((base_uri, DCTERMS.created, Literal(datetime.now().isoformat())))

    # Import core ontology
    core_path = ontology_root / "ontoclaw-core.ttl"
    if core_path.exists():
        g.add((base_uri, OWL.imports, URIRef(f"file://{core_path}")))

    # Import all skill modules
    for skill_path in skill_paths:
        skill_path = skill_path.resolve()
        g.add((base_uri, OWL.imports, URIRef(f"file://{skill_path}")))

    # Ensure output directory exists
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to file
    g.serialize(index_path, format="turtle")
    logger.info(f"Generated index manifest at {index_path} with {len(skill_paths)} skill imports")


# =============================================================================
# Orphan Cleanup
# =============================================================================

# System-generated files that should never be considered orphans
SYSTEM_FILES = {
    "ontoclaw-core.ttl",
    "index.ttl",
    "index.enabled.ttl",
    "index.installed.ttl",
    "registry.lock.json",
    "registry.sources.json",
}


def clean_orphaned_files(
    skills_dir: Path,
    output_dir: Path,
    dry_run: bool = False
) -> int:
    """
    Remove output files whose source no longer exists.

    Implements perfect mirror cleanup:
    - ontoskill.ttl → SKILL.md mapping
    - *.ttl → *.md mapping (for auxiliary markdown)
    - Direct asset mapping (non-ttl files)

    Args:
        skills_dir: Path to skills/ directory
        output_dir: Path to ontoskills/ directory
        dry_run: If True, log what would be deleted without deleting

    Returns:
        Count of orphaned files removed
    """
    orphans_removed = 0
    protected_dirs = {"system", "vendor", "official", "community"}

    # Find all files in output directory
    for output_file in output_dir.rglob("*"):
        if not output_file.is_file():
            continue

        # Skip system-generated files (core ontology, index manifest)
        if output_file.name in SYSTEM_FILES:
            continue

        # Compute relative path from output directory
        try:
            rel_path = output_file.relative_to(output_dir)
        except ValueError:
            continue

        if rel_path.parts and rel_path.parts[0] in protected_dirs:
            continue

        # Determine expected source path based on output file type
        if output_file.name == "ontoskill.ttl":
            # Rule A: ontoskill.ttl maps to SKILL.md
            source_path = skills_dir / rel_path.parent / "SKILL.md"
        elif output_file.suffix == ".ttl":
            # Rule B: *.ttl maps to *.md (auxiliary markdown)
            source_path = skills_dir / rel_path.with_suffix(".md")
        else:
            # Rule C: Asset files map directly
            source_path = skills_dir / rel_path

        # If source doesn't exist, this is an orphan
        if not source_path.exists():
            logger.info(f"Orphan found: {output_file} (source: {source_path} missing)")
            if not dry_run:
                output_file.unlink()
                logger.info(f"Removed orphan: {output_file}")
            orphans_removed += 1

    if orphans_removed > 0:
        action = "Would remove" if dry_run else "Removed"
        logger.info(f"{action} {orphans_removed} orphaned file(s)")
    else:
        logger.info("No orphaned files found")

    return orphans_removed
