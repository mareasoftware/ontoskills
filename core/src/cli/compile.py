"""Compile command - compile skills into modular ontology."""

import json
import logging
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rdflib import Graph, RDF
from rdflib.namespace import DCTERMS

from compiler.extractor import (
    generate_skill_id,
    generate_qualified_skill_id,
    generate_sub_skill_id,
    resolve_package_id,
    compute_sub_skill_hash,
)
from compiler.skill_registry import SkillRegistry
from compiler.transformer import tool_use_loop
from compiler.security import security_check, SecurityError
from compiler.core_ontology import get_oc_namespace, create_core_ontology
from compiler.serialization import serialize_skill_to_module
from compiler.storage import (
    clean_orphaned_files,
    generate_package_manifest,
    generate_registry_index,
)
from compiler.registry import (
    enabled_index_path,
    ensure_registry_layout,
)
from compiler.exceptions import (
    ExtractionError,
    SkillNotFoundError,
    OrphanSubSkillsError,
    OntologyValidationError,
)
from compiler.config import CORE_ONTOLOGY_FILENAME, SKILLS_DIR, OUTPUT_DIR, resolve_ontology_root, ANTHROPIC_MODEL
from compiler.loader import scan_skill_directory, LoaderError
from compiler.schemas import CompiledSkill

console = Console()
logger = logging.getLogger(__name__)


def find_skill_root_dir(start_path: Path, boundary_path: Path) -> Path | None:
    """Walk up from start_path to find the nearest ancestor containing SKILL.md.

    Args:
        start_path: Directory to start searching from
        boundary_path: Stop walking at this path (exclusive)

    Returns:
        The nearest parent directory containing SKILL.md, or None.
    """
    candidate = start_path.resolve()
    boundary = boundary_path.resolve()
    while candidate != boundary and candidate != candidate.parent:
        if (candidate / "SKILL.md").exists():
            return candidate
        candidate = candidate.parent
    return None


def infer_parent_skill_id(skill_dir: Path, input_path: Path, skill_parent_map: dict | None = None) -> str | None:
    """Infer the nearest parent skill from the directory structure.

    A nested skill inherits from the closest ancestor directory that contains
    its own `SKILL.md`. This makes inheritance deterministic and avoids relying
    on the extractor to rediscover obvious filesystem relationships.

    Args:
        skill_dir: Path to the skill directory
        input_path: Root input path
        skill_parent_map: Optional map of skill_dir -> (qualified_id, package_id)
                         to get canonical frontmatter-based skill IDs

    Returns:
        The canonical parent skill ID (from frontmatter if available) or None
    """
    # Normalize skill_parent_map keys for consistent lookups
    normalized_map: dict | None = None
    if skill_parent_map is not None:
        normalized_map = {Path(p).resolve(): v for p, v in skill_parent_map.items()}

    # Walk up from parent of skill_dir to find nearest SKILL.md
    parent_dir = find_skill_root_dir(skill_dir.resolve().parent, input_path.resolve())
    if parent_dir is None:
        return None

    if normalized_map is not None:
        if parent_dir in normalized_map:
            qualified_id, _ = normalized_map[parent_dir]
            return qualified_id.split('/')[-1]
        return None  # Parent has SKILL.md but failed Phase 1
    else:
        return generate_skill_id(parent_dir.name)


def enrich_extracted_skill(extracted, skill_dir: Path, input_path: Path, skill_parent_map: dict | None = None, skill_registry: SkillRegistry | None = None):
    """Apply deterministic compiler-side enrichments to extracted skills."""
    parent_skill_id = infer_parent_skill_id(skill_dir, input_path, skill_parent_map)
    if parent_skill_id and parent_skill_id != extracted.id and parent_skill_id not in extracted.extends:
        extracted.extends.append(parent_skill_id)
    if extracted.extends:
        extracted.depends_on = [
            dependency for dependency in extracted.depends_on
            if dependency not in extracted.extends
        ]
    # Filter relation references against known skills in this package
    if skill_registry:
        extracted.depends_on = skill_registry.filter_relations(extracted.depends_on, "depends_on")
        extracted.extends = skill_registry.filter_relations(extracted.extends, "extends")
        extracted.contradicts = skill_registry.filter_relations(extracted.contradicts, "contradicts")
    return extracted


# In-memory error collector for compile-errors.json (thread-safe)
_compile_errors: list[dict] = []
_errors_lock = threading.Lock()


def _record_error(skill_id: str, error: str, kind: str = "extraction") -> None:
    """Append a compile error to the in-memory collector."""
    with _errors_lock:
        _compile_errors.append({
            "skill_id": skill_id,
            "error": str(error),
            "kind": kind,
            "timestamp": datetime.now().isoformat(),
        })


def _write_error_log(output_path: Path) -> None:
    """Flush collected errors to compile-errors.json in the output directory."""
    if not _compile_errors:
        return
    error_file = output_path / "compile-errors.json"
    existing = []
    if error_file.exists():
        try:
            existing = json.loads(error_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    existing.extend(_compile_errors)
    error_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote {len(_compile_errors)} error(s) to {error_file}")


def _generate_manifests_from_disk(output_path: Path, ontology_root: Path) -> None:
    """Generate per-package package.json and root index.json by scanning TTLs on disk.

    Reads skill metadata (description, category, intents, extends) directly from
    compiled TTL files. Generates one package.json per sub-package directory and
    a root index.json listing all packages.

    Output layout:
        ontostore/
        ├── packages/
        │   └── anthropics/
        │       ├── financial-services-plugin/package.json
        │       ├── knowledge-work-plugins/package.json
        │       └── claude-code/package.json
        ├── system/
        └── index.json
    """
    from compiler.core_ontology import get_oc_namespace

    oc = get_oc_namespace()
    parent_skills = list(output_path.rglob("ontoskill.ttl"))
    all_ttls = list(output_path.rglob("*.ttl"))
    all_intents_jsons = list(output_path.rglob("intents.json"))

    if not parent_skills:
        return

    author_name = output_path.name
    # sub_pkg_dir -> list of skill dicts
    packages_on_disk: dict[Path, list[dict]] = {}

    def _extract_skill_id(uri_str: str) -> str:
        """Extract skill ID from a URI like https://ontoskills.sh/ontology#skill_pptx."""
        if "#" in uri_str:
            fragment = uri_str.rsplit("#", 1)[-1]
            if fragment.startswith("skill_"):
                fragment = fragment[6:]
            return fragment.replace("_", "-")
        return uri_str

    for ttl_path in parent_skills:
        rel = ttl_path.relative_to(output_path)
        graph = Graph()
        try:
            graph.parse(ttl_path, format="turtle")
        except Exception:
            continue

        for skill_uri in graph.subjects(RDF.type, oc.Skill):
            skill_id = str(graph.value(skill_uri, DCTERMS.identifier) or "")
            if not skill_id:
                continue

            # Use oc:hasDescription (the rich description), not oc:nature
            description = str(graph.value(skill_uri, oc.hasDescription) or "")
            category = str(graph.value(skill_uri, getattr(oc, 'hasCategory', None)) or "")
            extends = [_extract_skill_id(str(o)) for o in graph.objects(skill_uri, oc.extends)]
            depends = [_extract_skill_id(str(o)) for o in graph.objects(skill_uri, oc.dependsOnSkill)]
            intents = [str(o) for o in graph.objects(skill_uri, getattr(oc, 'resolvesIntent', None))]

            # Sub-package directory = first segment under author
            # e.g., rel = financial-services-plugin/funding-digest/ontoskill.ttl
            # → sub_pkg_dir = financial-services-plugin/
            parts = rel.parts
            if len(parts) >= 2:
                sub_pkg_dir = output_path / parts[0]
            else:
                sub_pkg_dir = output_path
            pkg_id = f"{author_name}/{parts[0]}" if len(parts) >= 2 else author_name

            # Collect all TTL modules under this skill's directory
            skill_dir = ttl_path.parent
            modules = []
            for t in all_ttls:
                try:
                    t.relative_to(skill_dir)
                    modules.append(str(t.relative_to(output_path)))
                except ValueError:
                    pass

            # Check for per-skill intents.json (produced by Block 1 embedding generation)
            embedding_file = ""
            skill_intents_json = skill_dir / "intents.json"
            if skill_intents_json in all_intents_jsons:
                embedding_file = str(skill_intents_json.relative_to(output_path))

            if sub_pkg_dir not in packages_on_disk:
                packages_on_disk[sub_pkg_dir] = []
            packages_on_disk[sub_pkg_dir].append({
                "skill_id": skill_id,
                "path": str(rel),
                "description": description.strip()[:500] if description else "",
                "category": category,
                "intents": intents,
                "aliases": [],
                "depends_on_skills": depends,
                "default_enabled": True,
                "modules": sorted(set(modules)),
                "embedding_file": embedding_file,
                "package_id": pkg_id,
            })

    # Generate per-sub-package package.json
    registry_packages = []
    for sub_pkg_dir, skills in packages_on_disk.items():
        pkg_id = skills[0]["package_id"] if skills else sub_pkg_dir.name
        # Write package.json into the sub-package directory
        generate_package_manifest(
            package_id=pkg_id,
            compiled_skills=skills,
            output_dir=sub_pkg_dir,
        )
        # Entry for root index.json
        try:
            rel_manifest = sub_pkg_dir.relative_to(ontology_root)
            manifest_path = f"{rel_manifest}/package.json"
        except ValueError:
            manifest_path = f"packages/{sub_pkg_dir.relative_to(output_path)}/package.json"
        registry_packages.append({
            "package_id": pkg_id,
            "manifest_path": manifest_path,
            "trust_tier": os.environ.get("ONTOSKILLS_TRUST_TIER", "community"),
            "source_kind": "ontology",
        })

    # Generate/update root index.json
    if registry_packages:
        generate_registry_index(registry_packages, ontology_root / "index.json")


MAX_EXTRACTION_RETRIES = 3


def retry_extraction(extract_fn, skill_id: str, *args, _max_retries: int = MAX_EXTRACTION_RETRIES, **kwargs):
    """Call extract_fn with retries on ExtractionError.

    Args:
        extract_fn: Callable that performs LLM extraction (e.g., tool_use_loop)
        skill_id: Skill identifier for logging
        _max_retries: Max retry attempts (default: MAX_EXTRACTION_RETRIES)
        *args, **kwargs: Forwarded to extract_fn

    Returns:
        The extraction result

    Raises:
        ExtractionError: After _max_retries failed attempts
    """
    last_error = None
    for attempt in range(1, _max_retries + 1):
        try:
            return extract_fn(*args, **kwargs)
        except ExtractionError as e:
            last_error = e
            if attempt < _max_retries:
                logger.warning(
                    f"Extraction attempt {attempt}/{_max_retries} failed for {skill_id}: {e}. Retrying..."
                )
            else:
                logger.error(
                    f"Extraction failed for {skill_id} after {_max_retries} attempts: {e}"
                )
    raise last_error

def _discover_author_dirs(input_path: Path) -> list[Path]:
    """Discover author subdirectories under a skills root.

    Each first-level subdirectory that contains SKILL.md files
    (at any depth) is treated as a separate author.
    """
    if not input_path.is_dir():
        return []
    author_dirs = []
    for child in sorted(input_path.iterdir()):
        if child.is_dir() and not child.name.startswith('.'):
            if any(child.rglob("SKILL.md")):
                author_dirs.append(child)
    return author_dirs


@click.command()
@click.argument('skill_name', required=False)
@click.option('-i', '--input', 'input_dir', default=SKILLS_DIR,
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for ontoskills')
@click.option('--dry-run', is_flag=True, help='Preview without saving')
@click.option('--skip-security', is_flag=True, help='Skip LLM security review (regex-based checks still run)')
@click.option('-f', '--force', is_flag=True,
              help='Force recompilation of all skills (bypass cache)')
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompt')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.option('--batch', is_flag=True,
              help='Treat input as a root of author directories; compile each subdirectory as a separate author')
@click.option('-w', '--workers', default=1, type=int,
              help='Number of parallel workers for skill extraction (default: 1)')
@click.option('--retries', '_retries', default=MAX_EXTRACTION_RETRIES, type=int,
              help=f'Max extraction retries per skill (default: {MAX_EXTRACTION_RETRIES})')
@click.option('--ontology-root', '_ontology_root', default=None, hidden=True,
              help='Override ontology root for system/ files (used internally by --batch)')
@click.pass_context
def compile_cmd(ctx, skill_name, input_dir, output_dir, dry_run, skip_security, force, yes, verbose, quiet, batch, workers, _retries, _ontology_root):
    """Compile skills into modular ontology with perfect mirroring.

    Without SKILL_NAME: Compile all files in input directory.
    With SKILL_NAME: Compile specific skill directory.
    With --batch: Auto-discover author subdirectories and compile each one.

    File Processing Rules:
      - SKILL.md → ontoskill.ttl (LLM compilation)
      - *.md → *.ttl (LLM compilation)
      - Other files → direct copy (assets)

    Output structure:
      ontoskills/
      ├── core.ttl
      ├── index.ttl
      └── <mirrored paths>/
          ├── ontoskill.ttl
          ├── *.ttl (auxiliary)
          └── <assets>
    """
    from . import setup_logging
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Reset error collector only for the outermost invocation.
    # Per-author invocations in batch mode accumulate into the same list.
    if batch:
        with _errors_lock:
            _compile_errors.clear()

    # Batch mode: discover author subdirectories and compile each one
    if batch:
        author_dirs = _discover_author_dirs(input_path)
        if not author_dirs:
            console.print(f"[yellow]No author directories with skills found in {input_path}[/yellow]")
            return
        # system/ lives at the same level as packages/ (sibling, not inside)
        batch_ontology_root = output_path.parent
        ensure_registry_layout(batch_ontology_root)

        total = len(author_dirs)
        console.print(f"[bold]Discovered {total} author(s) in {input_path}[/bold]")
        for i, author_dir in enumerate(author_dirs, 1):
            console.print(f"\n[bold cyan][{i}/{total}] Compiling {author_dir.name}[/bold cyan]")
            try:
                # Namespace each author under its name to avoid collisions
                author_output = output_path / author_dir.name
                ctx.invoke(
                    compile_cmd,
                    skill_name=None,
                    input_dir=str(author_dir),
                    output_dir=str(author_output),
                    dry_run=dry_run,
                    skip_security=skip_security,
                    force=force,
                    yes=True,  # auto-confirm for batch
                    verbose=verbose,
                    quiet=quiet,
                    batch=False,  # don't recurse
                    workers=workers,
                    _retries=_retries,
                    _ontology_root=str(batch_ontology_root),
                )
            except Exception as e:
                console.print(f"[red]Failed {author_dir.name}: {e}[/red]")
                _record_error(author_dir.name, str(e), "batch")
        # Flush error log
        _write_error_log(output_path)
        return

    ontology_root = Path(_ontology_root) if _ontology_root else (output_path.parent if output_dir != OUTPUT_DIR else resolve_ontology_root(output_path))
    ensure_registry_layout(ontology_root)

    # Clean orphaned files before compilation
    orphans_removed = clean_orphaned_files(input_path, output_path, dry_run=dry_run)
    if orphans_removed > 0:
        console.print(f"[yellow]Cleaned {orphans_removed} orphaned file(s)[/yellow]")

    # Find all files to process
    if skill_name:
        # Single skill directory - process all files within it
        skill_dir = input_path / skill_name
        if not skill_dir.exists():
            raise SkillNotFoundError(f"Skill directory not found: {skill_dir}")
        files_to_process = [f for f in skill_dir.rglob("*") if f.is_file()]
    else:
        # All files in input directory
        if not input_path.exists():
            console.print(f"[yellow]No skills directory found at {input_path}[/yellow]")
            return

        files_to_process = [f for f in input_path.rglob("*") if f.is_file()]

    if not files_to_process:
        console.print("[yellow]No files found in input directory[/yellow]")
        return

    logger.info(f"Found {len(files_to_process)} file(s) to process")

    # Categorize files by processing rule
    skill_md_files = []      # Rule A: SKILL.md → ontoskill.ttl
    auxiliary_md_files = []  # Rule B: *.md → *.ttl (excluding reference docs)
    asset_files = []         # Rule C: direct copy

    for file_path in files_to_process:
        # Apply same security filters as scan_skill_directory()
        # - Skip symlinked files to avoid copying external targets
        # - Skip paths with backslash (valid on POSIX but problematic)
        if file_path.is_symlink():
            continue
        rel_path = file_path.relative_to(input_path)
        if any('\\' in part for part in rel_path.parts):
            continue

        if file_path.name == "SKILL.md":
            skill_md_files.append(file_path)
        elif file_path.suffix == ".md":
            # Exclude reference/** paths - these are progressive disclosure docs, not sub-skills
            # They're already scanned in Phase 1 for hashing/metadata
            if "reference" in rel_path.parts:
                asset_files.append(file_path)  # Treat as asset, not sub-skill
            else:
                auxiliary_md_files.append(file_path)
        else:
            asset_files.append(file_path)

    logger.info(f"Core skills: {len(skill_md_files)}, Auxiliary md: {len(auxiliary_md_files)}, Assets: {len(asset_files)}")

    # OPTIONAL: load embedding model for per-skill embedding generation
    # Requires ontocore[embeddings] — skipped gracefully if not installed
    embedding_model = None
    if skill_md_files:
        try:
            from sentence_transformers import SentenceTransformer
            console.print("[blue]Loading embedding model for semantic search...[/blue]")
            embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        except ImportError:
            console.print(
                "[yellow]Skipping embedding generation[/yellow] "
                "(install with [bold]pip install ontocore[embeddings][/bold] to enable)"
            )

    # VALIDATION: Sub-skills require parent SKILL.md
    # Group files by directory and check each
    skill_dirs_with_auxiliary = {}
    for md_file in auxiliary_md_files:
        parent_dir = md_file.parent
        if parent_dir not in skill_dirs_with_auxiliary:
            skill_dirs_with_auxiliary[parent_dir] = []
        skill_dirs_with_auxiliary[parent_dir].append(md_file.name)

    for skill_dir, aux_files in skill_dirs_with_auxiliary.items():
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            # Auxiliary content directories (rules, examples, references, etc.)
            # within a valid skill tree are not orphans — just support content.
            logger.warning(
                "Directory '%s' has auxiliary .md files %s but no SKILL.md — treating as support content",
                skill_dir, aux_files,
            )

    # Counters for summary
    assets_copied = 0

    # Build skill_parent_map for Rule A using frontmatter names (not directory names)
    # This ensures parent/child IDs remain consistent
    # Also cache DirectoryScan results to avoid double scanning
    skill_parent_map = {}  # skill_dir -> (qualified_parent_id, package_id)
    dir_scan_cache = {}  # skill_dir -> DirectoryScan (cached from first pass)
    for skill_file in skill_md_files:
        skill_dir = skill_file.parent
        try:
            # Scan to get frontmatter name (canonical skill ID)
            dir_scan = scan_skill_directory(skill_dir)
            dir_scan_cache[skill_dir] = dir_scan  # Cache for reuse
            skill_id = dir_scan.skill_id  # From frontmatter.name
            package_id = resolve_package_id(skill_dir, input_path)
            qualified_parent_id = generate_qualified_skill_id(package_id, skill_id)
            skill_parent_map[skill_dir] = (qualified_parent_id, package_id)
        except LoaderError as e:
            # Phase 1 scan failed; do not add to skill_parent_map
            # so this directory cannot be selected as a parent during inheritance inference
            console.print(f"[red]Phase 1 scan failed while building parent map for {skill_dir.name}: {e}[/red]")
            continue

    # Build intra-package skill registry for LLM context + validation
    package_name = input_path.name if input_path else ""
    skill_registry = SkillRegistry.build(
        dir_scan_cache=dir_scan_cache,
        package_name=package_name,
    )
    logger.info(
        "Built skill registry with %d known skills for '%s'",
        len(skill_registry.skills), package_name,
    )

    # Thread-safe counters and collectors for parallel processing
    _counters_lock = threading.Lock()
    _skills_serialized = [0]
    _sub_skills_serialized = [0]
    _compiled_skills_list: list[CompiledSkill] = []

    def _process_rule_a(skill_file: Path) -> None:
        """Process a single Rule A skill (SKILL.md → ontoskill.ttl). Thread-safe."""
        skill_dir = skill_file.parent

        # Phase 1: Use cached scan result (or rescan if not cached)
        dir_scan = dir_scan_cache.get(skill_dir)
        if dir_scan is None:
            try:
                dir_scan = scan_skill_directory(skill_dir)
            except LoaderError as e:
                _record_error(skill_dir.name, str(e), "phase1")
                return

        # Use Phase 1 data for IDs and hash
        skill_id = dir_scan.skill_id
        skill_hash = dir_scan.content_hash
        package_id = resolve_package_id(skill_dir, input_path)

        logger.info(f"Processing skill: {skill_id}")

        # Compute output path
        rel_path = skill_dir.relative_to(input_path)
        output_skill_path = output_path / rel_path / "ontoskill.ttl"

        # Check if skill is unchanged (unless --force)
        if not force and output_skill_path.exists():
            existing_graph = Graph()
            try:
                existing_graph.parse(output_skill_path, format="turtle")
                oc = get_oc_namespace()
                for skill_uri in existing_graph.subjects(RDF.type, oc.Skill):
                    hash_val = existing_graph.value(skill_uri, oc.contentHash)
                    if hash_val and str(hash_val) == skill_hash:
                        logger.info(f"Skill {skill_id} unchanged (hash match), skipping")
                        return
            except Exception as e:
                logger.debug(f"Could not read existing skill: {e}")

        # Security check (use Phase 1 content)
        try:
            threats, passed = security_check(dir_scan.skill_md_content, skip_llm=skip_security)
            if not passed:
                _record_error(skill_id, "Security check failed", "security")
                return
        except SecurityError as e:
            _record_error(skill_id, str(e), "security")
            return

        # Phase 2: LLM extraction
        try:
            extracted = retry_extraction(
                tool_use_loop, skill_id,
                skill_dir, skill_hash, skill_id,
                skill_registry=skill_registry,
                preloaded_content=dir_scan.skill_md_content,
                preloaded_file_tree=dir_scan.file_tree,
                _max_retries=_retries,
            )
            extracted = enrich_extracted_skill(extracted, skill_dir, input_path, skill_parent_map, skill_registry)

            # Validate intents exist (mandatory for embedding generation)
            if not extracted.intents:
                _record_error(
                    skill_id,
                    f"Skill '{skill_id}' has no declared intents. "
                    "Every skill must declare at least one intent for semantic search.",
                    "embedding",
                )
                return

            # Create CompiledSkill with Phase 1 data
            compiled = CompiledSkill(
                **extracted.model_dump(),
                frontmatter=dir_scan.frontmatter,
                files=dir_scan.files,
            )

            # Serialize immediately to disk (unless dry_run)
            if not dry_run:
                _, pkg_id = skill_parent_map.get(skill_dir, (skill_id, "local"))
                qualified_id = f"{pkg_id}/{compiled.id}"
                try:
                    serialize_skill_to_module(
                        compiled, output_skill_path, output_path,
                        qualified_id=qualified_id
                    )
                    # Generate per-skill embeddings (optional)
                    if embedding_model is not None:
                        from compiler.embeddings.exporter import export_skill_embeddings
                        emb_path = export_skill_embeddings(output_skill_path, embedding_model)
                        logger.info(f"Generated embeddings for {skill_id}: {emb_path}")
                    with _counters_lock:
                        _skills_serialized[0] += 1
                        _compiled_skills_list.append(compiled)
                except OntologyValidationError as e:
                    _record_error(skill_id, str(e), "validation")
            else:
                with _counters_lock:
                    _compiled_skills_list.append(compiled)

            logger.info(f"Successfully extracted: {skill_id}")
        except ExtractionError as e:
            _record_error(skill_id, str(e), "main_skill")

    def _process_rule_b(md_file: Path) -> None:
        """Process a single Rule B sub-skill (*.md → *.ttl). Thread-safe."""
        # Walk up to find the parent skill directory (the one with SKILL.md)
        skill_dir = find_skill_root_dir(md_file.parent, input_path)
        if skill_dir is None:
            logger.warning(f"Skipping {md_file.name}: no parent SKILL.md found")
            return
        rel_path = md_file.relative_to(input_path)
        output_ttl_path = output_path / rel_path.with_suffix(".ttl")

        # Skip sub-skills whose parent failed Phase 1
        if skill_dir not in resolved_parent_map:
            logger.warning(f"Skipping {md_file.name}: parent not in skill_parent_map")
            return

        parent_qualified_id, package_id = resolved_parent_map[skill_dir]
        parent_local_id = parent_qualified_id.split('/')[-1] if '/' in parent_qualified_id else parent_qualified_id

        sub_skill_short_id = generate_skill_id(md_file.stem)
        sub_skill_qualified_id = generate_sub_skill_id(package_id, parent_local_id, md_file.name)
        sub_skill_hash = compute_sub_skill_hash(md_file)

        logger.info(f"Processing auxiliary markdown: {md_file.name} -> {sub_skill_short_id}")

        # Check cache
        if not force and output_ttl_path.exists():
            existing_graph = Graph()
            try:
                existing_graph.parse(output_ttl_path, format="turtle")
                oc = get_oc_namespace()
                for skill_uri in existing_graph.subjects(RDF.type, oc.Skill):
                    hash_val = existing_graph.value(skill_uri, oc.contentHash)
                    if hash_val and str(hash_val) == sub_skill_hash:
                        logger.info(f"Sub-skill {sub_skill_short_id} unchanged, skipping")
                        return
            except Exception as e:
                logger.debug(f"Could not read existing sub-skill: {e}")

        # Get sibling names for context
        sibling_names = [f.name for f in auxiliary_md_files if f.parent == skill_dir and f != md_file]

        parent_context = {
            "filename": md_file.name,
            "parent_skill_id": parent_qualified_id,
            "sibling_names": sibling_names
        }

        try:
            sub_skill_content = md_file.read_text(encoding="utf-8")
            extracted = retry_extraction(
                tool_use_loop, sub_skill_short_id,
                skill_dir, sub_skill_hash, sub_skill_short_id,
                parent_context=parent_context,
                skill_registry=skill_registry,
                preloaded_content=sub_skill_content,
                _max_retries=_retries,
            )
            extracted = enrich_extracted_skill(extracted, skill_dir, input_path, skill_parent_map, skill_registry)

            # Validate intents exist (mandatory for embedding generation)
            if not extracted.intents:
                _record_error(
                    sub_skill_short_id,
                    f"Skill '{sub_skill_short_id}' has no declared intents. "
                    "Every skill must declare at least one intent for semantic search.",
                    "embedding",
                )
                return

            if not dry_run:
                try:
                    serialize_skill_to_module(
                        extracted,
                        output_ttl_path,
                        output_path,
                        qualified_id=sub_skill_qualified_id,
                        extends_parent=parent_local_id,
                        extends_parent_qualified=parent_qualified_id,
                    )
                    # Generate per-skill embeddings (optional)
                    if embedding_model is not None:
                        from compiler.embeddings.exporter import export_skill_embeddings
                        emb_path = export_skill_embeddings(output_ttl_path, embedding_model)
                        logger.info(f"Generated embeddings for sub-skill {sub_skill_short_id}: {emb_path}")
                    with _counters_lock:
                        _sub_skills_serialized[0] += 1
                except OntologyValidationError as e:
                    _record_error(sub_skill_short_id, str(e), "validation")

            logger.info(f"Successfully extracted sub-skill: {sub_skill_short_id}")
        except ExtractionError as e:
            _record_error(sub_skill_short_id, str(e), "sub_skill")

    # Process Rule A: Core Skills (SKILL.md → ontoskill.ttl)
    if workers > 1 and len(skill_md_files) > 1:
        logger.info(f"Processing {len(skill_md_files)} Rule A skills with {workers} workers")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_rule_a, sf): sf for sf in skill_md_files}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    sf = futures[future]
                    _record_error(sf.parent.name, str(e), "rule_a_thread")
    else:
        for skill_file in skill_md_files:
            _process_rule_a(skill_file)

    # Process Rule B: Auxiliary Markdown (*.md → *.ttl)
    resolved_parent_map = {Path(p).resolve(): v for p, v in skill_parent_map.items()}
    if workers > 1 and len(auxiliary_md_files) > 1:
        logger.info(f"Processing {len(auxiliary_md_files)} Rule B sub-skills with {workers} workers")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_rule_b, mf): mf for mf in auxiliary_md_files}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    mf = futures[future]
                    _record_error(mf.name, str(e), "rule_b_thread")
    else:
        for md_file in auxiliary_md_files:
            _process_rule_b(md_file)

    # Process Rule C: Asset Files (collect for later - copy deferred until after dry_run check)
    assets_to_copy = []
    for asset_file in asset_files:
        rel_path = asset_file.relative_to(input_path)
        output_asset_path = output_path / rel_path

        # Skip if output exists and not forcing (for assets, check if same size)
        if output_asset_path.exists() and not force:
            if output_asset_path.stat().st_size == asset_file.stat().st_size:
                logger.debug(f"Asset unchanged, skipping: {asset_file.name}")
                continue

        assets_to_copy.append((asset_file, output_asset_path))

    # Show summary of extracted skills
    compiled_skills = _compiled_skills_list
    skills_serialized = _skills_serialized[0]
    sub_skills_serialized = _sub_skills_serialized[0]

    if compiled_skills:
        console.print(Panel(f"[green]Compiled {len(compiled_skills)} skill(s)[/green]"))

        for skill in compiled_skills:
            console.print(f"\n[bold]{skill.id}[/bold]")
            console.print(f"  Nature: {skill.nature[:80]}...")
            console.print(f"  Genus: {skill.genus}")
            console.print(f"  Intents: {', '.join(skill.intents)}")
            if skill.state_transitions and skill.state_transitions.requires_state:
                console.print(f"  Requires: {', '.join(skill.state_transitions.requires_state)}")
            if skill.state_transitions and skill.state_transitions.yields_state:
                console.print(f"  Yields: {', '.join(skill.state_transitions.yields_state)}")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes saved[/yellow]")
        return

    # Confirmation for single skill (only when a specific skill is requested)
    if skill_name and compiled_skills and not yes:
        if not click.confirm("\nAdd this skill to the ontology?", default=True):
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Copy assets (after dry_run check)
    for asset_file, output_asset_path in assets_to_copy:
        output_asset_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset_file, output_asset_path)
        assets_copied += 1
        logger.debug(f"Copied asset: {asset_file.name}")

    # Collect only parent skill output paths for index (ontoskill.ttl = parent, *.ttl = sub-skill)
    all_skill_paths = list(output_path.rglob("ontoskill.ttl"))

    # Flush error log to output directory
    _write_error_log(output_path)

    # Check for embedding errors (fatal — every skill must have embeddings)
    with _errors_lock:
        embedding_errors = [e for e in _compile_errors if e["kind"] == "embedding"]
    if embedding_errors:
        for err in embedding_errors:
            console.print(f"[red]{err['error']}[/red]")
        console.print("[red]Compilation failed: skills without declared intents.[/red]")
        raise SystemExit(1)

    # Generate per-package manifest (package.json) by scanning disk
    # This ensures manifests are always up-to-date even for skills skipped by hash match
    _generate_manifests_from_disk(output_path, ontology_root)

    # Summary output
    summary_parts = []
    if skills_serialized > 0:
        summary_parts.append(f"{skills_serialized} skill(s)")
    if sub_skills_serialized > 0:
        summary_parts.append(f"{sub_skills_serialized} sub-skill(s)")
    if assets_copied > 0:
        summary_parts.append(f"{assets_copied} asset(s)")

    if summary_parts:
        console.print(f"\n[green]Processed {', '.join(summary_parts)} to {output_path}[/green]")
        console.print(f"[green]Enabled index updated at {enabled_index_path(ontology_root)}[/green]")
    else:
        console.print("\n[yellow]No changes made[/yellow]")
