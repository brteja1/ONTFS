import os
from pathlib import Path
from ontfs.rdf_handler import OntFSGraph

class OntFS:
    def __init__(self, directory: str = "."):
        self.directory = Path(directory).resolve()
        # Lazily load graph to avoid error if not initialized for some commands
        self._graph = None
        
    @property
    def graph(self):
        if self._graph is None:
            self._graph = OntFSGraph(self.directory)
        return self._graph

    def init(self):
        try:
            g = OntFSGraph(self.directory)
            path = g.init_db()
            print(f"Initialized empty ontology graph in {path}")
        except FileExistsError as e:
            print(f"Error: {e}")
            
    def add_relation(self, uri: str, rel_type: str = None, 
                     is_transitive: bool = False, is_symmetric: bool = False,
                     subprop_of: str = None, inverse_of: str = None):
        self.graph.define_relation(
            uri_str=uri,
            rel_type=rel_type,
            is_transitive=is_transitive,
            is_symmetric=is_symmetric,
            subprop_of=subprop_of,
            inverse_of=inverse_of
        )
        self.graph.save()
        print(f"Relation {uri} defined successfully.")

    def link(self, subject: str, predicate: str, obj: str, obj_is_literal: bool = False):
        self.graph.add_triple(subject, predicate, obj, obj_is_literal)
        self.graph.save()
        print(f"Linked: {subject} -[{predicate}]-> {obj}")

    def unlink(self, subject: str, predicate: str, obj: str):
        self.graph.remove_triple(subject, predicate, obj)
        self.graph.save()
        print(f"Unlinked: {subject} -[{predicate}]-> {obj}")

    def query(self, query_str: str):
        # A simple pass-through to SPARQL for now
        # In the future, this can parse a simplified AST expression
        try:
            results = self.graph.query_graph(query_str)
            for row in results:
                print(" ".join([str(item) for item in row]))
        except Exception as e:
            print(f"Query Error: {e}")
