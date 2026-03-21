"""Tests for embeddings module."""

import json
import tempfile
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, Literal, RDF

from compiler.embeddings.exporter import extract_intents_from_ontology, export_embeddings, MODEL_NAME, EMBEDDING_DIM


OC = Namespace("https://ontoskills.sh/ontology#")
DCTERMS = Namespace("http://purl.org/dc/terms/")


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
    def test_export_embeddings_creates_files(self, tmp_path: Path):
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
