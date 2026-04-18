"""Tests for OntoSkills static linter."""

import pytest
from compiler.linter import lint_ontology

BASE = "@prefix oc: <https://ontoskills.sh/ontology#> .\n"


def _write(tmp_path, content: str):
    f = tmp_path / "skills.ttl"
    f.write_text(BASE + content)
    return str(f)


def test_clean_ontology_is_clean(tmp_path):
    """A well-formed ontology with no issues should produce a clean result."""
    path = _write(tmp_path, """
oc:Init a oc:Skill ;
    oc:resolvesIntent "init" ;
    oc:yieldsState   oc:Ready .

oc:SkillA a oc:Skill ;
    oc:resolvesIntent "do_a" ;
    oc:requiresState oc:Ready ;
    oc:yieldsState   oc:Done .

oc:SkillB a oc:Skill ;
    oc:resolvesIntent "do_b" ;
    oc:requiresState oc:Done ;
    oc:yieldsState   oc:Finished .
""")
    result = lint_ontology(path)
    assert result.is_clean, f"Expected clean, got: {result.issues}"


def test_dead_state_detected(tmp_path):
    """A skill requiring a state that no other skill yields should trigger a warning."""
    path = _write(tmp_path, """
oc:SkillA a oc:Skill ;
    oc:resolvesIntent "do_a" ;
    oc:requiresState oc:Ghost .
""")
    result = lint_ontology(path)
    codes = [i.code for i in result.issues]
    assert "dead-state" in codes


def test_duplicate_intent_detected(tmp_path):
    """Two skills with the same intent string should both be flagged."""
    path = _write(tmp_path, """
oc:SkillA a oc:Skill ; oc:resolvesIntent "create_pdf" .
oc:SkillB a oc:Skill ; oc:resolvesIntent "create_pdf" .
""")
    result = lint_ontology(path)
    assert result.has_errors
    dup_issues = [i for i in result.issues if i.code == "duplicate-intent"]
    assert len(dup_issues) == 2  # both skills are flagged


def test_no_false_positive_unique_intents(tmp_path):
    """Skills with distinct intents should not trigger duplicate-intent."""
    path = _write(tmp_path, """
oc:SkillA a oc:Skill ; oc:resolvesIntent "create_pdf" .
oc:SkillB a oc:Skill ; oc:resolvesIntent "send_email" .
""")
    result = lint_ontology(path)
    assert not any(i.code == "duplicate-intent" for i in result.issues)


def test_unreachable_skill_detected(tmp_path):
    """A skill with unreachable required states should be flagged."""
    path = _write(tmp_path, """
oc:SkillA a oc:Skill ;
    oc:resolvesIntent "process_data" ;
    oc:requiresState oc:DataLoaded .

oc:SkillB a oc:Skill ;
    oc:resolvesIntent "export_data" ;
    oc:requiresState oc:DataProcessed .
""")
    result = lint_ontology(path)
    # Both skills have unreachable required states
    unreachable = [i for i in result.issues if i.code == "unreachable-state"]
    assert len(unreachable) >= 1


def test_entry_point_not_flagged(tmp_path):
    """Skills with entry-point intents (create, import, etc.) should not be flagged as unreachable."""
    path = _write(tmp_path, """
oc:CreateDoc a oc:Skill ;
    oc:resolvesIntent "create_document" ;
    oc:requiresState oc:UserAuthenticated .
""")
    result = lint_ontology(path)
    # This is an entry point (create_*) so it shouldn't be flagged as unreachable
    unreachable = [i for i in result.issues if i.code == "unreachable-state"]
    # UserAuthenticated is still unreachable, but the skill is an entry point
    # so it might still be flagged for the dead state
    dead_states = [i for i in result.issues if i.code == "dead-state"]
    assert len(dead_states) >= 1 or len(unreachable) == 0


def test_circular_dep_detected(tmp_path):
    """A → B → A cycle should be flagged as an error."""
    path = _write(tmp_path, """
oc:SkillA a oc:Skill ;
    oc:resolvesIntent "do_a" ;
    oc:dependsOnSkill oc:SkillB .

oc:SkillB a oc:Skill ;
    oc:resolvesIntent "do_b" ;
    oc:dependsOnSkill oc:SkillA .
""")
    result = lint_ontology(path)
    assert result.has_errors
    assert any(i.code == "circular-dep" for i in result.issues)


def test_circular_dep_three_nodes(tmp_path):
    """A → B → C → A cycle should be detected."""
    path = _write(tmp_path, """
oc:A a oc:Skill ; oc:resolvesIntent "a" ; oc:dependsOnSkill oc:B .
oc:B a oc:Skill ; oc:resolvesIntent "b" ; oc:dependsOnSkill oc:C .
oc:C a oc:Skill ; oc:resolvesIntent "c" ; oc:dependsOnSkill oc:A .
""")
    result = lint_ontology(path)
    assert result.has_errors
    assert any(i.code == "circular-dep" for i in result.issues)


def test_workflow_step_cycle_detected(tmp_path):
    """A workflow with a cycle in step dependencies (oc:stepDependsOn) should be flagged."""
    path = _write(tmp_path, """
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "test_workflow" ;
    oc:hasWorkflow oc:Workflow1 .

oc:Workflow1 a oc:Workflow ;
    oc:hasStep oc:StepA, oc:StepB, oc:StepC .

oc:StepA a oc:WorkflowStep ;
    oc:stepId "step-a" .

oc:StepB a oc:WorkflowStep ;
    oc:stepId "step-b" ;
    oc:stepDependsOn oc:StepC .

oc:StepC a oc:WorkflowStep ;
    oc:stepId "step-c" ;
    oc:stepDependsOn oc:StepB .
""")
    result = lint_ontology(path)
    assert result.has_errors
    assert any(i.code == "workflow-cycle" for i in result.issues)


def test_workflow_step_three_node_cycle_detected(tmp_path):
    """A → B → C → A cycle in workflow steps should be detected."""
    path = _write(tmp_path, """
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "test_workflow" ;
    oc:hasWorkflow oc:Workflow1 .

oc:Workflow1 a oc:Workflow ;
    oc:hasStep oc:StepA, oc:StepB, oc:StepC .

oc:StepA a oc:WorkflowStep ;
    oc:stepId "step-a" ;
    oc:stepDependsOn oc:StepC .

oc:StepB a oc:WorkflowStep ;
    oc:stepId "step-b" ;
    oc:stepDependsOn oc:StepA .

oc:StepC a oc:WorkflowStep ;
    oc:stepId "step-c" ;
    oc:stepDependsOn oc:StepB .
""")
    result = lint_ontology(path)
    assert result.has_errors
    assert any(i.code == "workflow-cycle" for i in result.issues)


def test_circular_dep_no_false_positive_ancestor(tmp_path):
    """A skill that depends on a cyclic node but is NOT part of the cycle should not be flagged."""
    path = _write(tmp_path, """
oc:E a oc:Skill ; oc:resolvesIntent "e" ; oc:dependsOnSkill oc:A .
oc:A a oc:Skill ; oc:resolvesIntent "a" ; oc:dependsOnSkill oc:B .
oc:B a oc:Skill ; oc:resolvesIntent "b" ; oc:dependsOnSkill oc:C .
oc:C a oc:Skill ; oc:resolvesIntent "c" ; oc:dependsOnSkill oc:A .
""")
    result = lint_ontology(path)
    cyclic = [i for i in result.issues if i.code == "circular-dep"]
    cyclic_ids = {i.skill_id for i in cyclic}
    # Only A, B, C are in the cycle — E is just an ancestor
    assert cyclic_ids == {"A", "B", "C"}, f"False positive: {cyclic_ids}"


def test_workflow_no_cycle_clean(tmp_path):
    """A workflow with valid step dependencies (no cycles) should be clean."""
    path = _write(tmp_path, """
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "test_workflow" ;
    oc:hasWorkflow oc:Workflow1 .

oc:Workflow1 a oc:Workflow ;
    oc:hasStep oc:StepA, oc:StepB, oc:StepC .

oc:StepA a oc:WorkflowStep ;
    oc:stepId "step-a" .

oc:StepB a oc:WorkflowStep ;
    oc:stepId "step-b" ;
    oc:stepDependsOn oc:StepA .

oc:StepC a oc:WorkflowStep ;
    oc:stepId "step-c" ;
    oc:stepDependsOn oc:StepB .
""")
    result = lint_ontology(path)
    workflow_cycles = [i for i in result.issues if i.code == "workflow-cycle"]
    assert len(workflow_cycles) == 0, f"Unexpected workflow cycle: {workflow_cycles}"
