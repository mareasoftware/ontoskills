"""
State transition graph exporter for OntoSkills ontologies.

Reads the compiled ontology and produces a visual representation of the
skill state transition graph in Mermaid or DOT (Graphviz) format.

The graph shows how skills connect through states:
  - Skill A yieldsState X
  - Skill B requiresState X
  - Edge: A --> B (A enables B through state X)

This visualizes the actual execution flow between skills.

Usage:
    from compiler.graph_export import build_graph
    mermaid_src = build_graph(ttl_path, fmt="mermaid", skill_filter=None)
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import DCTERMS

OC = Namespace("https://ontoskills.sh/ontology#")


def build_graph(
    ttl_path: str | Path,
    fmt: str = "mermaid",
    skill_filter: str | None = None,
) -> str:
    """
    Build a state transition graph from a compiled ontology file.

    The graph shows skill connectivity through shared states:
    - An edge from Skill A to Skill B means A yieldsState X and B requiresState X
    - This visualizes the execution flow: A must complete before B can run

    Args:
        ttl_path:     Path to the .ttl file to analyse.
        fmt:          Output format — 'mermaid' or 'dot'.
        skill_filter: If given, include only this skill and its direct
                      neighbours (1-hop subgraph).

    Returns:
        A string containing the graph source in the requested format.
    """
    g = Graph()
    g.parse(str(ttl_path), format="turtle")

    nodes, edges = _extract_graph(g, skill_filter)

    if fmt == "dot":
        return _render_dot(nodes, edges)
    return _render_mermaid(nodes, edges)


# ─── Extraction ───────────────────────────────────────────────────────────────


def _local(uri) -> str:
    return str(uri).split("#")[-1].split("/")[-1]


def _extract_graph(
    g: Graph, skill_filter: str | None
) -> tuple[set[str], list[tuple[str, str, str]]]:
    """
    Return the set of node IDs and edge list (src, dst, state).

    Edges represent state transitions:
    - src yieldsState X, dst requiresState X
    - Edge: src --> dst (via state X)
    """
    edges: list[tuple[str, str, str]] = []

    # Build mapping: skill URI -> display ID (prefer dcterms:identifier, fallback to URI fragment)
    # Deduplicate URIs (skills with multiple intents appear multiple times in g.subjects)
    skills = list(dict.fromkeys(g.subjects(OC.resolvesIntent)))
    skill_uri_to_id: dict = {}
    for skill_uri in skills:
        display_id = g.value(skill_uri, DCTERMS.identifier)
        if display_id is not None:
            skill_uri_to_id[skill_uri] = str(display_id)
        else:
            skill_uri_to_id[skill_uri] = _local(skill_uri)

    # Build mapping: state -> skills that yield it
    state_to_producers: dict[str, list[str]] = {}
    for skill_uri in skills:
        skill_id = skill_uri_to_id[skill_uri]
        for state_uri in g.objects(skill_uri, OC.yieldsState):
            state = _local(state_uri)
            state_to_producers.setdefault(state, []).append(skill_id)

    # Build mapping: state -> skills that require it
    state_to_consumers: dict[str, list[str]] = {}
    for skill_uri in skills:
        skill_id = skill_uri_to_id[skill_uri]
        for state_uri in g.objects(skill_uri, OC.requiresState):
            state = _local(state_uri)
            state_to_consumers.setdefault(state, []).append(skill_id)

    # Create edges: producer --> consumer (via state)
    seen_edges: set[tuple[str, str, str]] = set()
    for state, consumers in state_to_consumers.items():
        producers = state_to_producers.get(state, [])
        for producer in producers:
            for consumer in consumers:
                edge = (producer, consumer, state)
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    edges.append(edge)

    # Ensure deterministic edge ordering for stable Mermaid/DOT output
    edges.sort()

    # Collect all nodes that have at least one intent (real skills)
    skill_ids = {skill_uri_to_id[s] for s in skills}

    # Apply 1-hop filter (against the same display IDs used in edges)
    if skill_filter:
        neighbours = {skill_filter}
        for src, dst, _ in edges:
            if src == skill_filter:
                neighbours.add(dst)
            if dst == skill_filter:
                neighbours.add(src)
        edges = [(s, d, r) for s, d, r in edges if s in neighbours and d in neighbours]
        skill_ids &= neighbours

    # Include edge endpoints even if they have no declared intents
    for src, dst, _ in edges:
        skill_ids.add(src)
        skill_ids.add(dst)

    return skill_ids, edges


# ─── Renderers ────────────────────────────────────────────────────────────────


def _render_mermaid(nodes: set[str], edges: list[tuple[str, str, str]]) -> str:
    """Render as a Mermaid flowchart (TD orientation)."""
    lines = ["graph TD"]

    for node in sorted(nodes):
        lines.append(f'  {node}["{node}"]')

    for src, dst, state in edges:
        # Edge shows which state enables the transition
        lines.append(f"  {src} -->|{state}| {dst}")

    return "\n".join(lines)


def _render_dot(nodes: set[str], edges: list[tuple[str, str, str]]) -> str:
    """Render as a Graphviz DOT digraph."""
    lines = [
        "digraph OntoSkills {",
        "  rankdir=TD;",
        '  node [shape=box, style=filled, fillcolor="#e8f4f8", fontname="Helvetica"];',
    ]

    for node in sorted(nodes):
        lines.append(f'  "{node}";')

    for src, dst, state in edges:
        # Edge shows which state enables the transition
        lines.append(f'  "{src}" -> "{dst}" [label="{state}"];')

    lines.append("}")
    return "\n".join(lines)
