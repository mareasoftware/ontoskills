import pytest
from loader import create_ontology_graph
from rdflib import Graph


def test_create_ontology_graph():
    graph = create_ontology_graph()
    assert isinstance(graph, Graph)
    # Check that basic prefixes are bound
    prefixes = dict(graph.namespaces())
    assert "ag" in prefixes
