import os
import urllib.parse
from pathlib import Path
from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import SKOS, OWL, RDF, RDFS
from ontfs.namespaces import bind_namespaces, CUSTOM, ONTFS

DB_FILE = ".ontfs.ttl"

class OntFSGraph:
    def __init__(self, directory: str = "."):
        self.directory = Path(directory).resolve()
        self.db_path = self.directory / DB_FILE
        self.graph = Graph()
        bind_namespaces(self.graph)
        self.is_dirty = False
        self._load()

    def _load(self):
        if self.db_path.exists():
            self.graph.parse(self.db_path, format="turtle")

    def save(self):
        if self.is_dirty:
            self.graph.serialize(destination=self.db_path, format="turtle")
            self.is_dirty = False

    def init_db(self):
        if self.db_path.exists():
            raise FileExistsError(f"{DB_FILE} already exists in {self.directory}")
        # Just create an empty graph and save it
        self.is_dirty = True
        self.save()
        return self.db_path

    def resolve_uri(self, uri_str: str) -> URIRef:
        """
        Converts a string into an rdflib URIRef.
        - Handles prefixed names (e.g., custom:dependsOn)
        - Handles local file paths by converting them to file:// URIs
        - Handles explicit web URLs
        """
        # If it looks like a prefix, resolve it
        if ":" in uri_str and not uri_str.startswith(("http://", "https://", "file://", "urn:")):
            prefix, name = uri_str.split(":", 1)
            for p, ns in self.graph.namespaces():
                if p == prefix:
                    return URIRef(ns + name)
            
            # fallback: treat as raw URI if prefix not found?
            pass
        
        # If it's a web url or explicit file url
        if uri_str.startswith(("http://", "https://", "file://", "urn:")):
            return URIRef(uri_str)
        
        # Otherwise, treat as a local file path
        # Make it absolute based on the current graph directory
        abs_path = (self.directory / uri_str).resolve()
        return URIRef(abs_path.as_uri())

    def add_triple(self, s_str: str, p_str: str, o_str: str, o_is_literal: bool = False):
        s = self.resolve_uri(s_str)
        p = self.resolve_uri(p_str)
        if o_is_literal:
            o = Literal(o_str)
        else:
            o = self.resolve_uri(o_str)
            
        self.graph.add((s, p, o))
        self.is_dirty = True

    def remove_triple(self, s_str: str, p_str: str, o_str: str):
        s = self.resolve_uri(s_str)
        p = self.resolve_uri(p_str)
        # Assuming object is URI for unlink command mostly
        o = self.resolve_uri(o_str)
        
        self.graph.remove((s, p, o))
        self.is_dirty = True

    def define_relation(self, uri_str: str, rel_type: str = None, 
                        is_transitive: bool = False, is_symmetric: bool = False,
                        subprop_of: str = None, inverse_of: str = None):
        """Helper to set OWL axioms on a property"""
        p = self.resolve_uri(uri_str)
        
        if rel_type == "object":
            self.graph.add((p, RDF.type, OWL.ObjectProperty))
        elif rel_type == "datatype":
            self.graph.add((p, RDF.type, OWL.DatatypeProperty))
            
        if is_transitive:
            self.graph.add((p, RDF.type, OWL.TransitiveProperty))
        if is_symmetric:
            self.graph.add((p, RDF.type, OWL.SymmetricProperty))
            
        if subprop_of:
            self.graph.add((p, RDFS.subPropertyOf, self.resolve_uri(subprop_of)))
            
        if inverse_of:
            self.graph.add((p, OWL.inverseOf, self.resolve_uri(inverse_of)))
            
        self.is_dirty = True

    def query_graph(self, query_str: str):
        """Execute a SPARQL query"""
        return self.graph.query(query_str)
