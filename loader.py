import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from rdflib.namespace import DCTERMS, SKOS, PROV

AG = Namespace("http://agentic.web/ontology#")


def create_ontology_graph() -> Graph:
    g = Graph()
    g.bind("ag", AG)
    g.bind("owl", OWL)
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)

    ontology_uri = rdflib.URIRef("http://agentic.web/ontology")
    g.add((ontology_uri, RDF.type, OWL.Ontology))
    g.add((ontology_uri, DCTERMS.title, rdflib.Literal("Agentic Skills Ontology")))

    g.add((AG.Skill, RDF.type, OWL.Class))
    g.add((AG.Tool, RDF.type, OWL.Class))
    g.add((AG.Tool, RDFS.subClassOf, AG.Skill))

    return g
