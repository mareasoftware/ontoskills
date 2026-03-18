"""Tests for OntoClaw skill explainer."""

from compiler.explainer import explain_skill, list_skill_ids

BASE = """
@prefix oc:      <https://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
"""

TTL = BASE + """
oc:CreatePDF a oc:ExecutableSkill ;
    dcterms:identifier "create-pdf" ;
    oc:nature          "Generates a PDF document from structured input" ;
    oc:resolvesIntent  "create_pdf" ;
    oc:resolvesIntent  "generate_pdf" ;
    oc:requiresState   oc:FileExists ;
    oc:yieldsState     oc:PDFCreated ;
    oc:handlesFailure  oc:OperationFailed ;
    oc:hasRequirement  oc:req_abc123 ;
    oc:impartsKnowledge oc:kn_xyz789 ;
    oc:generatedBy     "claude-opus-4-6" ;
    oc:contentHash     "abc12345xyz" ;
    oc:hasPayload      oc:CreatePDFPayload .

oc:CreatePDFPayload a oc:ExecutionPayload ;
    oc:executor "python" .

oc:req_abc123 a oc:Requirement ;
    oc:requirementValue "pypdf" ;
    oc:isOptional false .

oc:kn_xyz789 a oc:PreFlightCheck ;
    oc:directiveContent "Always validate PDF structure before manipulation" ;
    oc:appliesToContext "When opening PDF files for editing" ;
    oc:hasRationale "Corrupted PDFs can cause silent data loss" ;
    oc:severityLevel "HIGH" .

oc:ReadFile a oc:DeclarativeSkill ;
    dcterms:identifier "read-file" ;
    oc:nature          "Reads a file from disk" ;
    oc:resolvesIntent  "read_file" .
"""


def _write(tmp_path, content=TTL):
    f = tmp_path / "skills.ttl"
    f.write_text(content)
    return str(f)


def test_explain_returns_summary(tmp_path):
    """explain_skill should return a populated SkillSummary for a known skill."""
    summary = explain_skill(_write(tmp_path), "create-pdf")
    assert summary is not None
    assert summary.skill_id == "create-pdf"


def test_explain_skill_type(tmp_path):
    """ExecutableSkill subclass should be reflected in skill_type."""
    summary = explain_skill(_write(tmp_path), "create-pdf")
    assert summary.skill_type == "ExecutableSkill"


def test_explain_intents(tmp_path):
    """All declared intents should be present in the summary."""
    summary = explain_skill(_write(tmp_path), "create-pdf")
    assert "create_pdf" in summary.intents
    assert "generate_pdf" in summary.intents


def test_explain_states(tmp_path):
    """requiresState, yieldsState, and handlesFailure should be populated."""
    summary = explain_skill(_write(tmp_path), "create-pdf")
    assert "FileExists" in summary.requires_states
    assert "PDFCreated" in summary.yields_states
    assert "OperationFailed" in summary.handles_failures


def test_explain_requirements(tmp_path):
    """Requirements should be extracted from hasRequirement nodes."""
    summary = explain_skill(_write(tmp_path), "create-pdf")
    assert len(summary.requirements) == 1
    req = summary.requirements[0]
    assert req.requirement_value == "pypdf"
    assert req.is_optional is False


def test_explain_knowledge_nodes(tmp_path):
    """Knowledge nodes should be extracted from impartsKnowledge."""
    summary = explain_skill(_write(tmp_path), "create-pdf")
    assert len(summary.knowledge_nodes) == 1
    kn = summary.knowledge_nodes[0]
    assert kn.node_type == "PreFlightCheck"
    assert "validate PDF structure" in kn.directive_content
    assert kn.severity_level == "HIGH"


def test_explain_executor(tmp_path):
    """Executor type should be extracted from the payload node."""
    summary = explain_skill(_write(tmp_path), "create-pdf")
    assert summary.executor == "python"


def test_explain_hash_truncated(tmp_path):
    """Content hash should be truncated to 8 characters."""
    summary = explain_skill(_write(tmp_path), "create-pdf")
    assert summary.content_hash == "abc12345"


def test_explain_unknown_skill_returns_none(tmp_path):
    """explain_skill should return None for a non-existent skill ID."""
    result = explain_skill(_write(tmp_path), "does-not-exist")
    assert result is None


def test_list_skill_ids(tmp_path):
    """list_skill_ids should return all skill identifiers in the ontology."""
    ids = list_skill_ids(_write(tmp_path))
    assert "create-pdf" in ids
    assert "read-file" in ids
