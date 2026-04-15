"""Tests for embeddings module."""

import json
import tempfile
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, Literal, RDF

from compiler.embeddings.exporter import extract_intents_from_ontology, MODEL_NAME, EMBEDDING_DIM

# sentence_transformers is an optional dependency — skip export tests if missing
try:
    import sentence_transformers  # noqa: F401
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


OC = Namespace("https://ontoskills.sh/ontology#")
DCTERMS = Namespace("http://purl.org/dc/terms/")


def _make_skill_ttl(skill_id: str, intents: list[str]) -> str:
    """Helper to create a minimal skill TTL with given intents."""
    g = Graph()
    g.bind("oc", OC)
    g.bind("dcterms", DCTERMS)

    skill = OC[skill_id]
    g.add((skill, RDF.type, OC.Skill))
    g.add((skill, DCTERMS.identifier, Literal(skill_id)))
    for intent in intents:
        g.add((skill, OC.resolvesIntent, Literal(intent)))

    return g.serialize(format="turtle")


class TestExtractIntents:
    """Tests for intent extraction from ontology."""

    def test_extract_intents_single_skill(self, tmp_path: Path):
        """Extract intents from a single skill with dcterms:identifier."""
        # Create test ontology using production format with dcterms:identifier
        g = Graph()
        g.bind("oc", OC)
        g.bind("dcterms", DCTERMS)

        skill = OC["skill_test"]
        g.add((skill, RDF.type, OC.Skill))
        g.add((skill, DCTERMS.identifier, Literal("test-skill")))  # Production format
        g.add((skill, OC.resolvesIntent, Literal("create_pdf")))

        ontology_path = tmp_path / "test.ttl"
        g.serialize(ontology_path, format="turtle")

        # Extract intents
        intents = extract_intents_from_ontology(ontology_path)

        assert len(intents) == 1
        assert intents[0]["intent"] == "create_pdf"
        assert "test-skill" in intents[0]["skills"]  # Should use identifier, not URI

    def test_extract_intents_multiple_skills_same_intent(self, tmp_path: Path):
        """Multiple skills can resolve the same intent."""
        g = Graph()
        g.bind("oc", OC)
        g.bind("dcterms", DCTERMS)

        skill1 = OC["skill_a"]
        skill2 = OC["skill_b"]
        g.add((skill1, RDF.type, OC.Skill))
        g.add((skill1, DCTERMS.identifier, Literal("skill-a")))
        g.add((skill1, OC.resolvesIntent, Literal("send_email")))
        g.add((skill2, RDF.type, OC.Skill))
        g.add((skill2, DCTERMS.identifier, Literal("skill-b")))
        g.add((skill2, OC.resolvesIntent, Literal("send_email")))

        ontology_path = tmp_path / "test.ttl"
        g.serialize(ontology_path, format="turtle")

        intents = extract_intents_from_ontology(ontology_path)

        assert len(intents) == 1
        assert intents[0]["intent"] == "send_email"
        assert len(intents[0]["skills"]) == 2
        assert "skill-a" in intents[0]["skills"]
        assert "skill-b" in intents[0]["skills"]

    def test_extract_intents_fallback_to_uri(self, tmp_path: Path):
        """Fallback to URI fragment when dcterms:identifier is missing."""
        g = Graph()
        g.bind("oc", OC)
        # No dcterms:identifier - should use URI fragment

        skill = OC["legacy-skill"]
        g.add((skill, RDF.type, OC.Skill))
        g.add((skill, OC.resolvesIntent, Literal("legacy_action")))

        ontology_path = tmp_path / "test.ttl"
        g.serialize(ontology_path, format="turtle")

        intents = extract_intents_from_ontology(ontology_path)

        assert len(intents) == 1
        assert intents[0]["intent"] == "legacy_action"
        assert "legacy-skill" in intents[0]["skills"]  # Falls back to URI fragment

    def test_extract_intents_no_intents(self, tmp_path: Path):
        """Return empty list when no intents exist."""
        g = Graph()
        g.bind("oc", OC)

        skill = OC["orphan-skill"]
        g.add((skill, RDF.type, OC.Skill))
        # No resolvesIntent

        ontology_path = tmp_path / "test.ttl"
        g.serialize(ontology_path, format="turtle")

        intents = extract_intents_from_ontology(ontology_path)

        assert intents == []


class TestExportEmbeddings:
    """Tests for full embedding export."""

    @pytest.mark.integration
    @pytest.mark.skipif(not HAS_SENTENCE_TRANSFORMERS, reason="sentence_transformers not installed")
    def test_export_embeddings_creates_files(self, tmp_path: Path):
        from compiler.embeddings.exporter import export_embeddings
        """Export creates all required files with production format."""
        # Create test ontology with intents using production format
        g = Graph()
        g.bind("oc", OC)
        g.bind("dcterms", DCTERMS)

        skill = OC["skill_pdf"]
        g.add((skill, RDF.type, OC.Skill))
        g.add((skill, DCTERMS.identifier, Literal("pdf")))  # Production format
        g.add((skill, OC.resolvesIntent, Literal("create_pdf")))
        g.add((skill, OC.resolvesIntent, Literal("export_document")))

        ontology_root = tmp_path / "ontoskills"
        ontology_root.mkdir()
        (ontology_root / "index.ttl").write_text(g.serialize(format="turtle"))

        output_dir = tmp_path / "embeddings"

        export_embeddings(ontology_root, output_dir)

        assert (output_dir / "intents.json").exists()

        with open(output_dir / "intents.json") as f:
            data = json.load(f)

        assert data["model"] == MODEL_NAME
        assert data["dimension"] == EMBEDDING_DIM
        assert len(data["intents"]) == 2

        for intent_entry in data["intents"]:
            assert "intent" in intent_entry
            assert "embedding" in intent_entry
            assert len(intent_entry["embedding"]) == EMBEDDING_DIM
            assert "skills" in intent_entry
            assert "pdf" in intent_entry["skills"]  # Should use identifier


class TestExportSkillEmbeddings:
    """Tests for per-skill embedding export (mandatory at compile time)."""

    @pytest.mark.skipif(not HAS_SENTENCE_TRANSFORMERS, reason="sentence_transformers not installed")
    def test_export_skill_embeddings_writes_intents_json(self, tmp_path: Path):
        """Per-skill export writes intents.json next to ontoskill.ttl."""
        from sentence_transformers import SentenceTransformer
        from compiler.embeddings.exporter import export_skill_embeddings

        # Create a skill TTL with intents
        ttl_content = _make_skill_ttl("my-skill", ["create_pdf", "export_document"])
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        ttl_path = skill_dir / "ontoskill.ttl"
        ttl_path.write_text(ttl_content)

        model = SentenceTransformer(MODEL_NAME)
        result_path = export_skill_embeddings(ttl_path, model)

        assert result_path == skill_dir / "intents.json"
        assert result_path.exists()

        with open(result_path) as f:
            data = json.load(f)

        assert data["model"] == MODEL_NAME
        assert data["dimension"] == EMBEDDING_DIM
        assert len(data["intents"]) == 2
        assert data["intents"][0]["intent"] in ("create_pdf", "export_document")
        assert len(data["intents"][0]["embedding"]) == EMBEDDING_DIM
        assert "my-skill" in data["intents"][0]["skills"]

    @pytest.mark.skipif(not HAS_SENTENCE_TRANSFORMERS, reason="sentence_transformers not installed")
    def test_export_skill_embeddings_no_intents_raises(self, tmp_path: Path):
        """Per-skill export raises ValueError when skill has no intents."""
        from sentence_transformers import SentenceTransformer
        from compiler.embeddings.exporter import export_skill_embeddings

        # Create a skill TTL WITHOUT intents
        g = Graph()
        g.bind("oc", OC)
        g.bind("dcterms", DCTERMS)
        skill = OC["orphan-skill"]
        g.add((skill, RDF.type, OC.Skill))
        g.add((skill, DCTERMS.identifier, Literal("orphan-skill")))

        skill_dir = tmp_path / "orphan-skill"
        skill_dir.mkdir()
        ttl_path = skill_dir / "ontoskill.ttl"
        ttl_path.write_text(g.serialize(format="turtle"))

        model = SentenceTransformer(MODEL_NAME)

        with pytest.raises(ValueError, match="no declared intents"):
            export_skill_embeddings(ttl_path, model)

    @pytest.mark.skipif(not HAS_SENTENCE_TRANSFORMERS, reason="sentence_transformers not installed")
    def test_export_skill_embeddings_format_matches_mcp(self, tmp_path: Path):
        """intents.json format must match what MCP Rust EmbeddingEngine::load() expects."""
        from sentence_transformers import SentenceTransformer
        from compiler.embeddings.exporter import export_skill_embeddings

        ttl_content = _make_skill_ttl("search-skill", ["search documents"])
        skill_dir = tmp_path / "search-skill"
        skill_dir.mkdir()
        ttl_path = skill_dir / "ontoskill.ttl"
        ttl_path.write_text(ttl_content)

        model = SentenceTransformer(MODEL_NAME)
        result_path = export_skill_embeddings(ttl_path, model)

        with open(result_path) as f:
            data = json.load(f)

        # Verify structure expected by EmbeddingEngine::load() in embeddings.rs
        assert isinstance(data["model"], str)
        assert isinstance(data["dimension"], int)
        assert data["dimension"] == 384
        assert isinstance(data["intents"], list)
        assert len(data["intents"]) >= 1

        for entry in data["intents"]:
            assert isinstance(entry["intent"], str)
            assert isinstance(entry["embedding"], list)
            assert len(entry["embedding"]) == data["dimension"]
            assert all(isinstance(v, (int, float)) for v in entry["embedding"])
            assert isinstance(entry["skills"], list)
            assert len(entry["skills"]) >= 1

    def test_compile_succeeds_without_sentence_transformers(self, tmp_path: Path):
        """ontocore compile should succeed (skipping embeddings) when sentence_transformers missing."""
        from unittest.mock import patch, MagicMock
        from click.testing import CliRunner
        from compiler.cli import cli

        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: Test\n---\n# Test", encoding="utf-8"
        )

        output_dir = tmp_path / "ontoskills"

        runner = CliRunner()
        # Remove sentence_transformers from importable modules so the
        # try/except ImportError in compile.py triggers the skip path.
        import sys
        st_modules = {k: v for k, v in sys.modules.items() if k.startswith("sentence_transformers")}
        for k in st_modules:
            del sys.modules[k]

        result = runner.invoke(cli, [
            'compile',
            '-i', str(tmp_path / "skills"),
            '-o', str(output_dir),
            '--skip-security',
            '-y',
        ])

        # Restore if they were present before
        sys.modules.update(st_modules)

        assert result.exit_code == 0
