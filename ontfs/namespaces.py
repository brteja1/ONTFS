from rdflib import Namespace
from rdflib.namespace import SKOS, OWL, RDF, RDFS

# Define standard namespaces
ONTFS = Namespace("http://ontfs.example.org/core#")
CUSTOM = Namespace("http://ontfs.example.org/custom#")

def bind_namespaces(graph):
    """Binds standard prefixes to the rdflib Graph."""
    graph.bind("skos", SKOS)
    graph.bind("owl", OWL)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("ontfs", ONTFS)
    graph.bind("custom", CUSTOM)
