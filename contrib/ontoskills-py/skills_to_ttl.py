#!/usr/bin/env python3
"""
skills_to_ttl.py — Convert our skill.md files to OntoSkills-compatible TTL.

Reads skill frontmatter (YAML) from devops-agent, research-lab, and wisp
skill files, generates minimal OWL 2 ontologies that OntoMCP can load.

No LLM extraction needed — we use the structured metadata already in our skills.

Usage:
    python skills_to_ttl.py --skills-dir ~/Documents/devops-agent/skills --output ~/.ontoskills/devops/
"""

import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

# ── RDF/Turtle templates ─────────────────────────────────────────────

PREFIXES = """@prefix oc: <https://ontoskills.sh/ontology#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
"""

SKILL_TEMPLATE = """
oc:skill_{skill_id} a oc:Skill ;
    rdfs:label "{name}" ;
    dct:description "{description}" ;
    dcterms:identifier "{skill_id}" ;
    oc:nature "{nature}" ;
    oc:nature "{nature}" ;
    oc:resolvesIntent "{intent}" .
"""

PAYLOAD_TEMPLATE = """[
    a oc:ExecutionPayload ;
    oc:executor "{executor}" ;
    oc:code \"\"\"{code}\"\"\"
]"""

DEPENDENCY_TEMPLATE = """
oc:{skill_id} oc:dependsOn oc:{dep_id} .
"""

CONTRADICT_TEMPLATE = """
oc:{skill_id} oc:contradicts oc:{dep_id} .
"""

EXTENSION_TEMPLATE = """
oc:{skill_id} oc:extends oc:{parent_id} .
"""


def slugify(text: str) -> str:
    """Convert skill name to a valid ontology ID."""
    return re.sub(r'[^a-z0-9-]', '-', text.lower().strip()).strip('-')


def escape_ttl_string(text: str) -> str:
    """Escape a string for use in Turtle literals."""
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def parse_frontmatter(path: Path) -> Optional[dict]:
    """Extract YAML frontmatter from a skill.md file."""
    text = path.read_text(encoding='utf-8')
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return None
    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None


def generate_ttl(skill_dir: Path, meta: dict, source_path: Path) -> str:
    """Generate TTL content for a single skill from its metadata."""
    name = meta.get('name', skill_dir.name)
    skill_id = slugify(name)
    description = escape_ttl_string(meta.get('description', ''))
    intent = escape_ttl_string(meta.get('applies_when', description)[:200])
    nature = escape_ttl_string(description[:200])  # Required by ontomcp SPARQL

    lines = [PREFIXES, f"# Skill: {name}"]

    # Skill definition
    skill_subject = f"oc:skill_{skill_id}"
    lines.append(f"""
{skill_subject} a oc:Skill ;
    rdfs:label "{escape_ttl_string(name)}" ;
    dct:description "{description}" ;
    dcterms:identifier "{skill_id}" ;
    oc:nature "{nature}" ;
    oc:nature "{nature}" ;
    oc:resolvesIntent "{intent}" .""")

    # Dependencies from requires field
    requires = meta.get('requires', [])
    if isinstance(requires, str):
        requires = [requires]
    for dep in requires:
        dep_id = slugify(dep)
        lines.append(f"\n{skill_subject} oc:dependsOn oc:skill_{dep_id} .")

    # Models as dependencies
    models = meta.get('models', {})
    if isinstance(models, dict):
        preferred = models.get('preferred', '')
        if preferred:
            lines.append(f'\n{skill_subject} oc:preferredModel "{preferred}" .')

    # Tools as hasPayload
    tools = meta.get('tools', meta.get('sandbox', {}).get('tools', []))
    if isinstance(tools, list) and tools:
        for tool in tools:
            lines.append(f'\n{skill_subject} oc:requiresTool "{escape_ttl_string(tool)}" .')

    # Sandbox info
    sandbox = meta.get('sandbox', {})
    if isinstance(sandbox, dict):
        network = sandbox.get('network', '')
        if network:
            lines.append(f'\n{skill_subject} oc:sandboxNetwork "{network}" .')
        domains = sandbox.get('allowed_domains', [])
        for domain in domains:
            lines.append(f'\n{skill_subject} oc:allowedDomain "{domain}" .')

    # Provenance
    timestamp = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()[:16]
    lines.append(f'\n{skill_subject} oc:generatedAt "{timestamp}" ;')
    lines.append(f'    oc:hash "{content_hash}" ;')
    lines.append(f'    oc:provenance "{skill_dir.name}/skill.md" .')

    return '\n'.join(lines) + '\n'


def convert_skills(skills_dir: str, output_dir: str) -> int:
    """Convert all skill.md files in a directory to TTL ontologies.

    Returns number of skills converted.
    """
    skills_path = Path(skills_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for skill_md in sorted(skills_path.rglob('skill.md')):
        meta = parse_frontmatter(skill_md)
        if not meta:
            print(f"  ⚠️  Skipping {skill_md}: no valid frontmatter")
            continue

        ttl_content = generate_ttl(skill_md.parent, meta, skill_md)
        skill_name = slugify(meta.get('name', skill_md.parent.name))
        ttl_path = output_path / f"{skill_name}.ttl"
        ttl_path.write_text(ttl_content, encoding='utf-8')
        print(f"  ✅ {skill_name}.ttl")
        count += 1

    # Generate index.ttl
    index_lines = [PREFIXES]
    for ttl_file in sorted(output_path.glob('*.ttl')):
        if ttl_file.name == 'index.ttl':
            continue
        content = ttl_file.read_text(encoding='utf-8')
        index_lines.append(content)

    index_path = output_path / 'index.ttl'
    index_path.write_text('\n'.join(index_lines), encoding='utf-8')
    print(f"  📋 index.ttl ({count} skills)")

    # Generate index.enabled.ttl (copy of index for ontomcp)
    enabled_path = output_path / 'system' / 'index.enabled.ttl'
    enabled_path.parent.mkdir(parents=True, exist_ok=True)
    enabled_path.write_text('\n'.join(index_lines), encoding='utf-8')

    return count


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Convert skill.md files to OntoSkills TTL')
    parser.add_argument('--skills-dir', '-i', required=True, help='Skills directory')
    parser.add_argument('--output', '-o', required=True, help='Output directory for TTL files')
    args = parser.parse_args()

    print(f"Converting skills from {args.skills_dir} → {args.output}")
    count = convert_skills(args.skills_dir, args.output)
    print(f"\nDone: {count} skills converted")
