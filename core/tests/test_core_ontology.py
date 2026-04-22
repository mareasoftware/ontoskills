"""
Tests for the core_ontology module.

These tests verify the OntoSkills core ontology (TBox) creation including:
- Namespace configuration
- Core class definitions (Skill, State, Attempt, ExecutionPayload)
- State transition properties
- Execution payload properties
- Skill relationship properties
- Predefined core and failure states
"""
import pytest
from pathlib import Path
from rdflib import Graph, RDF, RDFS, OWL, Namespace, Literal, XSD

from compiler.core_ontology import get_oc_namespace, create_core_ontology
from compiler.config import BASE_URI, CORE_STATES, FAILURE_STATES


class TestGetOcNamespace:
    """Tests for get_oc_namespace function."""

    def test_returns_namespace(self):
        """Test that get_oc_namespace returns a Namespace instance."""
        oc = get_oc_namespace()
        assert isinstance(oc, Namespace)

    def test_namespace_uses_base_uri(self):
        """Test that namespace uses configured BASE_URI."""
        oc = get_oc_namespace()
        assert str(oc) == BASE_URI

    def test_namespace_can_create_uris(self):
        """Test that namespace can create URI references."""
        oc = get_oc_namespace()
        skill_uri = oc.Skill
        assert str(skill_uri) == BASE_URI + "Skill"


class TestCreateCoreOntology:
    """Tests for create_core_ontology function."""

    def test_creates_graph(self, tmp_path):
        """Test that create_core_ontology returns a Graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        assert isinstance(graph, Graph)

    def test_creates_file(self, tmp_path):
        """Test that create_core_ontology creates the output file."""
        output_path = tmp_path / "core.ttl"
        create_core_ontology(output_path)
        assert output_path.exists()

    def test_creates_parent_directories(self, tmp_path):
        """Test that create_core_ontology creates parent directories if needed."""
        output_path = tmp_path / "nested" / "dir" / "core.ttl"
        create_core_ontology(output_path)
        assert output_path.exists()
        assert output_path.parent.is_dir()

    def test_uses_default_output_path(self, tmp_path):
        """Test that create_core_ontology uses default path when None provided."""
        # When output_path is None, it uses OUTPUT_DIR/core.ttl
        # This test verifies the function doesn't error with None
        graph = create_core_ontology(None)
        assert isinstance(graph, Graph)

    def test_graph_has_triples(self, tmp_path):
        """Test that the created graph has triples."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        assert len(graph) > 0


class TestCoreClasses:
    """Tests for core class definitions in the ontology."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoSkills namespace."""
        return get_oc_namespace()

    def test_skill_class_defined(self, core_ontology, oc):
        """Test that oc:Skill class is defined."""
        assert (oc.Skill, RDF.type, OWL.Class) in core_ontology
        assert (oc.Skill, RDFS.label, None) in core_ontology

    def test_executable_skill_class_defined(self, core_ontology, oc):
        """Test that oc:ExecutableSkill class is defined as subclass of Skill."""
        assert (oc.ExecutableSkill, RDF.type, OWL.Class) in core_ontology
        assert (oc.ExecutableSkill, RDFS.subClassOf, oc.Skill) in core_ontology

    def test_declarative_skill_class_defined(self, core_ontology, oc):
        """Test that oc:DeclarativeSkill class is defined as subclass of Skill."""
        assert (oc.DeclarativeSkill, RDF.type, OWL.Class) in core_ontology
        assert (oc.DeclarativeSkill, RDFS.subClassOf, oc.Skill) in core_ontology

    def test_state_class_defined(self, core_ontology, oc):
        """Test that oc:State class is defined."""
        assert (oc.State, RDF.type, OWL.Class) in core_ontology

    def test_attempt_class_defined(self, core_ontology, oc):
        """Test that oc:Attempt class is defined."""
        assert (oc.Attempt, RDF.type, OWL.Class) in core_ontology

    def test_execution_payload_class_defined(self, core_ontology, oc):
        """Test that oc:ExecutionPayload class is defined."""
        assert (oc.ExecutionPayload, RDF.type, OWL.Class) in core_ontology


class TestStateTransitionProperties:
    """Tests for state transition property definitions."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoSkills namespace."""
        return get_oc_namespace()

    def test_requires_state_property(self, core_ontology, oc):
        """Test oc:requiresState property (Skill -> State)."""
        assert (oc.requiresState, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.requiresState, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.requiresState, RDFS.range, oc.State) in core_ontology

    def test_yields_state_property(self, core_ontology, oc):
        """Test oc:yieldsState property (Skill -> State)."""
        assert (oc.yieldsState, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.yieldsState, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.yieldsState, RDFS.range, oc.State) in core_ontology

    def test_handles_failure_property(self, core_ontology, oc):
        """Test oc:handlesFailure property (Skill -> State)."""
        assert (oc.handlesFailure, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.handlesFailure, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.handlesFailure, RDFS.range, oc.State) in core_ontology

    def test_has_status_property(self, core_ontology, oc):
        """Test oc:hasStatus property (Attempt -> State)."""
        assert (oc.hasStatus, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.hasStatus, RDFS.domain, oc.Attempt) in core_ontology
        assert (oc.hasStatus, RDFS.range, oc.State) in core_ontology


class TestExecutionPayloadProperties:
    """Tests for execution payload property definitions."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoSkills namespace."""
        return get_oc_namespace()

    def test_has_payload_property(self, core_ontology, oc):
        """Test oc:hasPayload property (Skill -> ExecutionPayload)."""
        assert (oc.hasPayload, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.hasPayload, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.hasPayload, RDFS.range, oc.ExecutionPayload) in core_ontology

    def test_executor_property(self, core_ontology, oc):
        """Test oc:executor datatype property."""
        assert (oc.executor, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.executor, RDFS.domain, oc.ExecutionPayload) in core_ontology

    def test_code_property(self, core_ontology, oc):
        """Test oc:code datatype property."""
        assert (oc.code, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.code, RDFS.domain, oc.ExecutionPayload) in core_ontology

    def test_timeout_property(self, core_ontology, oc):
        """Test oc:timeout datatype property."""
        assert (oc.timeout, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.timeout, RDFS.domain, oc.ExecutionPayload) in core_ontology


class TestSkillRelationshipProperties:
    """Tests for skill relationship property definitions."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoSkills namespace."""
        return get_oc_namespace()

    def test_depends_on_property(self, core_ontology, oc):
        """Test oc:dependsOn asymmetric property with inverse."""
        assert (oc.dependsOn, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.dependsOn, RDF.type, OWL.AsymmetricProperty) in core_ontology
        assert (oc.dependsOn, OWL.inverseOf, oc.enables) in core_ontology

    def test_enables_property(self, core_ontology, oc):
        """Test oc:enables property (inverse of dependsOn)."""
        assert (oc.enables, RDF.type, OWL.ObjectProperty) in core_ontology

    def test_depends_on_is_deprecated(self, core_ontology, oc):
        """oc:dependsOn should be marked as owl:deprecated."""
        assert (oc.dependsOn, OWL.deprecated, Literal(True)) in core_ontology

    def test_depends_on_skill_has_inverse(self, core_ontology, oc):
        """oc:dependsOnSkill should have owl:inverseOf oc:enablesSkill."""
        assert (oc.dependsOnSkill, OWL.inverseOf, oc.enablesSkill) in core_ontology

    def test_enables_skill_property(self, core_ontology, oc):
        """Test oc:enablesSkill property (inverse of dependsOnSkill)."""
        assert (oc.enablesSkill, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.enablesSkill, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.enablesSkill, RDFS.range, oc.Skill) in core_ontology

    def test_extends_property(self, core_ontology, oc):
        """Test oc:extends transitive property."""
        assert (oc.extends, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.extends, RDF.type, OWL.TransitiveProperty) in core_ontology

    def test_is_extended_by_property(self, core_ontology, oc):
        """Test oc:isExtendedBy property (inverse of extends)."""
        assert (oc.isExtendedBy, RDF.type, OWL.ObjectProperty) in core_ontology

    def test_contradicts_property(self, core_ontology, oc):
        """Test oc:contradicts symmetric property."""
        assert (oc.contradicts, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.contradicts, RDF.type, OWL.SymmetricProperty) in core_ontology


class TestAdditionalSkillProperties:
    """Tests for additional skill property definitions."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoSkills namespace."""
        return get_oc_namespace()

    def test_generated_by_property(self, core_ontology, oc):
        """Test oc:generatedBy datatype property for LLM attestation."""
        assert (oc.generatedBy, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.generatedBy, RDFS.domain, oc.Skill) in core_ontology

    def test_content_hash_property(self, core_ontology, oc):
        """Test oc:contentHash datatype property."""
        assert (oc.contentHash, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.contentHash, RDFS.domain, oc.Skill) in core_ontology

    def test_nature_property(self, core_ontology, oc):
        """Test oc:nature datatype property."""
        assert (oc.nature, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.nature, RDFS.domain, oc.Skill) in core_ontology

    def test_differentia_property(self, core_ontology, oc):
        """Test oc:differentia datatype property."""
        assert (oc.differentia, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.differentia, RDFS.domain, oc.Skill) in core_ontology

    def test_resolves_intent_property(self, core_ontology, oc):
        """Test oc:resolvesIntent datatype property."""
        assert (oc.resolvesIntent, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.resolvesIntent, RDFS.domain, oc.Skill) in core_ontology

    def test_has_constraint_property(self, core_ontology, oc):
        """Test oc:hasConstraint datatype property."""
        assert (oc.hasConstraint, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.hasConstraint, RDFS.domain, oc.Skill) in core_ontology


class TestPredefinedStates:
    """Tests for predefined core and failure states."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoSkills namespace."""
        return get_oc_namespace()

    def test_core_states_defined(self, core_ontology, oc):
        """Test that all core states are defined as subclasses of State."""
        for state_name, state_fragment in CORE_STATES.items():
            state_uri = oc[state_fragment.lstrip('#')]
            assert (state_uri, RDF.type, OWL.Class) in core_ontology
            assert (state_uri, RDFS.subClassOf, oc.State) in core_ontology

    def test_failure_states_defined(self, core_ontology, oc):
        """Test that all failure states are defined as subclasses of State."""
        for state_name, state_fragment in FAILURE_STATES.items():
            state_uri = oc[state_fragment.lstrip('#')]
            assert (state_uri, RDF.type, OWL.Class) in core_ontology
            assert (state_uri, RDFS.subClassOf, oc.State) in core_ontology

    def test_core_states_have_labels(self, core_ontology, oc):
        """Test that core states have RDFS labels."""
        from rdflib import Literal
        for state_name, state_fragment in CORE_STATES.items():
            state_uri = oc[state_fragment.lstrip('#')]
            assert (state_uri, RDFS.label, Literal(state_name)) in core_ontology

    def test_failure_states_have_labels(self, core_ontology, oc):
        """Test that failure states have RDFS labels."""
        from rdflib import Literal
        for state_name, state_fragment in FAILURE_STATES.items():
            state_uri = oc[state_fragment.lstrip('#')]
            assert (state_uri, RDFS.label, Literal(state_name)) in core_ontology


class TestOntologyHeader:
    """Tests for ontology header/metadata."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    def test_ontology_has_type(self, core_ontology):
        """Test that the ontology has OWL.Ontology type."""
        from rdflib import URIRef
        base_uri = URIRef(BASE_URI.rstrip('#'))
        assert (base_uri, RDF.type, OWL.Ontology) in core_ontology

    def test_ontology_has_title(self, core_ontology):
        """Test that the ontology has a title."""
        from rdflib import URIRef
        from rdflib.namespace import DCTERMS
        base_uri = URIRef(BASE_URI.rstrip('#'))
        assert (base_uri, DCTERMS.title, None) in core_ontology

    def test_ontology_has_description(self, core_ontology):
        """Test that the ontology has a description."""
        from rdflib import URIRef
        from rdflib.namespace import DCTERMS
        base_uri = URIRef(BASE_URI.rstrip('#'))
        assert (base_uri, DCTERMS.description, None) in core_ontology

    def test_namespaces_bound(self, core_ontology):
        """Test that required namespaces are bound in the graph."""
        prefixes = dict(core_ontology.namespaces())
        assert "oc" in prefixes
        assert "owl" in prefixes
        assert "rdf" in prefixes
        assert "rdfs" in prefixes
        assert "dcterms" in prefixes
        assert "skos" in prefixes
        assert "prov" in prefixes


class TestKnowledgeNodeHierarchy:
    """Tests for 10-dimensional KnowledgeNode TBox hierarchy."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoSkills namespace."""
        return get_oc_namespace()

    def test_knowledge_node_base_class_defined(self, core_ontology, oc):
        """Test that oc:KnowledgeNode base class is defined."""
        assert (oc.KnowledgeNode, RDF.type, OWL.Class) in core_ontology
        assert (oc.KnowledgeNode, RDFS.label, None) in core_ontology

    def test_ten_dimension_subclasses_exist(self, core_ontology, oc):
        """Test that all 10 dimension subclasses exist."""
        dimensions = [
            "NormativeRule", "StrategicInsight", "ResilienceTactic",
            "ExecutionPhysics", "Observability", "SecurityGuardrail",
            "CognitiveBoundary", "ResourceProfile", "TrustMetric", "LifecycleHook"
        ]
        for dim in dimensions:
            assert (oc[dim], RDF.type, OWL.Class) in core_ontology
            assert (oc[dim], RDFS.subClassOf, oc.KnowledgeNode) in core_ontology

    def test_concrete_types_normative_rule(self, core_ontology, oc):
        """Test NormativeRule concrete types: Standard, AntiPattern, Constraint."""
        assert (oc.Standard, RDF.type, OWL.Class) in core_ontology
        assert (oc.Standard, RDFS.subClassOf, oc.NormativeRule) in core_ontology
        assert (oc.AntiPattern, RDF.type, OWL.Class) in core_ontology
        assert (oc.AntiPattern, RDFS.subClassOf, oc.NormativeRule) in core_ontology
        assert (oc.Constraint, RDF.type, OWL.Class) in core_ontology
        assert (oc.Constraint, RDFS.subClassOf, oc.NormativeRule) in core_ontology

    def test_concrete_types_strategic_insight(self, core_ontology, oc):
        """Test StrategicInsight concrete types."""
        assert (oc.Heuristic, RDF.type, OWL.Class) in core_ontology
        assert (oc.Heuristic, RDFS.subClassOf, oc.StrategicInsight) in core_ontology
        assert (oc.DesignPrinciple, RDF.type, OWL.Class) in core_ontology
        assert (oc.WorkflowStrategy, RDF.type, OWL.Class) in core_ontology

    def test_concrete_types_lifecycle_hook(self, core_ontology, oc):
        """Test LifecycleHook concrete types."""
        assert (oc.PreFlightCheck, RDF.type, OWL.Class) in core_ontology
        assert (oc.PostFlightValidation, RDF.type, OWL.Class) in core_ontology
        assert (oc.RollbackProcedure, RDF.type, OWL.Class) in core_ontology


class TestKnowledgeNodeProperties:
    """Tests for KnowledgeNode property definitions."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoSkills namespace."""
        return get_oc_namespace()

    def test_imparts_knowledge_object_property(self, core_ontology, oc):
        """Test oc:impartsKnowledge object property (Skill -> KnowledgeNode)."""
        assert (oc.impartsKnowledge, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.impartsKnowledge, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.impartsKnowledge, RDFS.range, oc.KnowledgeNode) in core_ontology

    def test_directive_content_datatype_property(self, core_ontology, oc):
        """Test oc:directiveContent datatype property."""
        assert (oc.directiveContent, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.directiveContent, RDFS.domain, oc.KnowledgeNode) in core_ontology

    def test_applies_to_context_datatype_property(self, core_ontology, oc):
        """Test oc:appliesToContext datatype property."""
        assert (oc.appliesToContext, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.appliesToContext, RDFS.domain, oc.KnowledgeNode) in core_ontology

    def test_has_rationale_datatype_property(self, core_ontology, oc):
        """Test oc:hasRationale datatype property."""
        assert (oc.hasRationale, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.hasRationale, RDFS.domain, oc.KnowledgeNode) in core_ontology

    def test_severity_level_datatype_property(self, core_ontology, oc):
        """Test oc:severityLevel datatype property."""
        assert (oc.severityLevel, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.severityLevel, RDFS.domain, oc.KnowledgeNode) in core_ontology


class TestKnowledgeRBoxAxioms:
    """Tests for RBox axioms for knowledge inheritance."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoSkills namespace."""
        return get_oc_namespace()

    def test_imparts_knowledge_asymmetric(self, core_ontology, oc):
        """Test that impartsKnowledge is asymmetric."""
        assert (oc.impartsKnowledge, RDF.type, OWL.AsymmetricProperty) in core_ontology

    def test_imparts_knowledge_irreflexive(self, core_ontology, oc):
        """Test that impartsKnowledge is irreflexive."""
        assert (oc.impartsKnowledge, RDF.type, OWL.IrreflexiveProperty) in core_ontology

    def test_inherits_knowledge_super_property(self, core_ontology, oc):
        """Test that inheritsKnowledge is a super-property of impartsKnowledge."""
        assert (oc.inheritsKnowledge, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.impartsKnowledge, RDFS.subPropertyOf, oc.inheritsKnowledge) in core_ontology

    def test_property_chain_axiom_exists(self, core_ontology, oc):
        """Test that property chain axiom for knowledge inheritance exists."""
        # The axiom is: extends o impartsKnowledge ⊑ inheritsKnowledge
        # Check that the triple exists (the object will be a BNode for the list)
        assert any((oc.inheritsKnowledge, OWL.propertyChainAxiom, obj) in core_ontology
                   for obj in core_ontology.objects(oc.inheritsKnowledge, OWL.propertyChainAxiom))


class TestContentBlockClasses:
    """Tests for content block OWL classes and properties."""

    def test_code_example_class_exists(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.CodeExample, RDF.type, OWL.Class) in graph

    def test_table_class_exists(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.Table, RDF.type, OWL.Class) in graph

    def test_flowchart_class_exists(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.Flowchart, RDF.type, OWL.Class) in graph

    def test_template_class_exists(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.Template, RDF.type, OWL.Class) in graph

    def test_has_code_example_property(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.hasCodeExample, RDF.type, OWL.ObjectProperty) in graph
        assert (oc.hasCodeExample, RDFS.domain, oc.Skill) in graph
        assert (oc.hasCodeExample, RDFS.range, oc.CodeExample) in graph

    def test_has_table_property(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.hasTable, RDF.type, OWL.ObjectProperty) in graph

    def test_has_flowchart_property(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.hasFlowchart, RDF.type, OWL.ObjectProperty) in graph

    def test_has_template_property(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.hasTemplate, RDF.type, OWL.ObjectProperty) in graph

    def test_code_content_datatype_property(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.codeContent, RDF.type, OWL.DatatypeProperty) in graph

    def test_step_order_property(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        graph = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.stepOrder, RDF.type, OWL.DatatypeProperty) in graph
        assert (oc.stepOrder, RDFS.domain, oc.WorkflowStep) in graph


class TestContentModelOntology:
    """Tests for content model classes — Section, Paragraph, BulletList, BlockQuote."""

    def test_section_class_exists(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.Section, RDF.type, OWL.Class) in g

    def test_section_datatype_properties(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.sectionTitle, RDF.type, OWL.DatatypeProperty) in g
        assert (oc.sectionLevel, RDF.type, OWL.DatatypeProperty) in g
        assert (oc.sectionOrder, RDF.type, OWL.DatatypeProperty) in g

    def test_section_object_properties(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.hasSection, RDF.type, OWL.ObjectProperty) in g
        assert (oc.hasSubsection, RDF.type, OWL.ObjectProperty) in g
        assert (oc.hasContent, RDF.type, OWL.ObjectProperty) in g

    def test_paragraph_class_and_properties(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.Paragraph, RDF.type, OWL.Class) in g
        assert (oc.textContent, RDF.type, OWL.DatatypeProperty) in g
        assert (oc.contentOrder, RDF.type, OWL.DatatypeProperty) in g

    def test_bullet_list_class_and_properties(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.BulletList, RDF.type, OWL.Class) in g
        assert (oc.BulletItem, RDF.type, OWL.Class) in g
        assert (oc.hasItem, RDF.type, OWL.ObjectProperty) in g
        assert (oc.itemText, RDF.type, OWL.DatatypeProperty) in g
        assert (oc.itemOrder, RDF.type, OWL.DatatypeProperty) in g

    def test_blockquote_class_and_properties(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.BlockQuote, RDF.type, OWL.Class) in g
        assert (oc.quoteContent, RDF.type, OWL.DatatypeProperty) in g
        assert (oc.quoteAttribution, RDF.type, OWL.DatatypeProperty) in g


class TestContentBlockOntology:
    """Tests for content block classes — HTMLBlock, FrontmatterBlock, hasChild."""

    def test_html_block_class_and_properties(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.HTMLBlock, RDF.type, OWL.Class) in g
        assert (oc.htmlContent, RDF.type, OWL.DatatypeProperty) in g

    def test_frontmatter_block_class_and_properties(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.FrontmatterBlock, RDF.type, OWL.Class) in g
        assert (oc.rawYaml, RDF.type, OWL.DatatypeProperty) in g

    def test_has_child_property(self, tmp_path):
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.hasChild, RDF.type, OWL.ObjectProperty) in g


class TestOperationalNodeOntology:
    """Tests for operational knowledge node types and properties."""

    def test_operational_node_classes_exist(self, tmp_path):
        """Procedure, CodePattern, OutputFormat, Command, Prerequisite are KnowledgeNode subclasses."""
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        for node_type in ["Procedure", "CodePattern", "OutputFormat", "Command", "Prerequisite"]:
            assert (oc[node_type], RDF.type, OWL.Class) in g, f"Missing class: {node_type}"
            assert (oc[node_type], RDFS.subClassOf, oc.KnowledgeNode) in g, f"{node_type} not subclass of KnowledgeNode"

    def test_operational_node_properties_exist(self, tmp_path):
        """codeLanguage, stepOrder, templateVariables exist as DatatypeProperties."""
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        for prop_name in ["codeLanguage", "stepOrder", "templateVariables"]:
            assert (oc[prop_name], RDF.type, OWL.DatatypeProperty) in g, f"Missing property: {prop_name}"

    def test_step_order_has_integer_range(self, tmp_path):
        """stepOrder should have xsd:integer range."""
        output_path = tmp_path / "core.ttl"
        g = create_core_ontology(output_path)
        oc = get_oc_namespace()
        assert (oc.stepOrder, RDFS.range, XSD.integer) in g
