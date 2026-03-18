"""Tests for OntoClaw state transition graph exporter."""

from compiler.graph_export import build_graph

BASE = "@prefix oc: <https://ontoclaw.marea.software/ontology#> .\n"

# State transition graph: SkillA yields Ready, SkillB requires Ready
TTL = BASE + """
oc:SkillA a oc:Skill ;
    oc:resolvesIntent "a" ;
    oc:requiresState oc:Idle ;
    oc:yieldsState   oc:Ready .

oc:SkillB a oc:Skill ;
    oc:resolvesIntent "b" ;
    oc:requiresState oc:Ready ;
    oc:yieldsState   oc:Done .

oc:SkillC a oc:Skill ;
    oc:resolvesIntent "c" ;
    oc:requiresState oc:Done ;
    oc:yieldsState   oc:Finished .

oc:Isolated a oc:Skill ;
    oc:resolvesIntent "isolated" .
"""


def _write(tmp_path, content=TTL):
    f = tmp_path / "skills.ttl"
    f.write_text(content)
    return str(f)


def test_mermaid_contains_all_nodes(tmp_path):
    """All four skills should appear as Mermaid nodes."""
    out = build_graph(_write(tmp_path), fmt="mermaid")
    for skill in ("SkillA", "SkillB", "SkillC", "Isolated"):
        assert skill in out


def test_mermaid_state_transition_arrow(tmp_path):
    """A yields Ready, B requires Ready → A -->|Ready| B."""
    out = build_graph(_write(tmp_path), fmt="mermaid")
    assert "SkillA -->|Ready| SkillB" in out
    assert "SkillB -->|Done| SkillC" in out


def test_dot_format(tmp_path):
    """DOT output should start with 'digraph' and show state transitions."""
    out = build_graph(_write(tmp_path), fmt="dot")
    assert out.startswith("digraph OntoClaw")
    assert '"SkillA"' in out
    assert "Ready" in out


def test_skill_filter_limits_output(tmp_path):
    """--skill filter should include only the target skill and its neighbours."""
    out = build_graph(_write(tmp_path), fmt="mermaid", skill_filter="SkillB")
    assert "SkillB" in out
    assert "SkillA" in out   # produces Ready that SkillB requires
    assert "SkillC" in out   # requires Done that SkillB yields
    assert "Isolated" not in out  # no state connection to SkillB


def test_empty_ontology(tmp_path):
    """An ontology with no state transitions should produce a valid but edge-free graph."""
    path = tmp_path / "empty.ttl"
    path.write_text(BASE + "oc:Alone a oc:Skill ; oc:resolvesIntent \"x\" .\n")
    out = build_graph(str(path), fmt="mermaid")
    assert "graph TD" in out
    assert "-->" not in out


def test_multiple_skills_same_state(tmp_path):
    """Multiple skills requiring the same state should all connect to producers."""
    path = tmp_path / "multi.ttl"
    path.write_text(BASE + """
oc:Producer a oc:Skill ;
    oc:resolvesIntent "produce" ;
    oc:yieldsState oc:Ready .

oc:Consumer1 a oc:Skill ;
    oc:resolvesIntent "consume1" ;
    oc:requiresState oc:Ready .

oc:Consumer2 a oc:Skill ;
    oc:resolvesIntent "consume2" ;
    oc:requiresState oc:Ready .
""")
    out = build_graph(str(path), fmt="mermaid")
    assert "Producer -->|Ready| Consumer1" in out
    assert "Producer -->|Ready| Consumer2" in out
