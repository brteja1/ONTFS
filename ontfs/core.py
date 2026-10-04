import os
import json
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


    def add_relations(self, file_path: str):
        import json
        with open(file_path, 'r') as f:
            relations = json.load(f)

        for rel in relations:
            self.graph.define_relation(
                uri_str=rel['uri'],
                rel_type=rel.get('type'),
                is_transitive=rel.get('transitive', False),
                is_symmetric=rel.get('symmetric', False),
                subprop_of=rel.get('subprop_of'),
                inverse_of=rel.get('inverse') or rel.get('inverse_of')
            )
        self.graph.save()
        print(f"Batch defined {len(relations)} relations successfully.")

    def link(self, subject: str, predicate: str, obj: str, obj_is_literal: bool = False):
        fact_id = self.graph.add_triple(subject, predicate, obj, obj_is_literal)
        self.graph.save()
        print(f"Linked: {subject} -[{predicate}]-> {obj}")
        return fact_id

    def remember(self, subject: str, predicate: str, obj: str,
                 obj_is_literal: bool = False, source: str = None,
                 confidence: float = None, asserted_by: str = None,
                 note: str = None, observed_at: str = None):
        """Assert a fact and attach agent-oriented explainability metadata."""
        s = self.graph.resolve_uri(subject)
        p = self.graph.resolve_uri(predicate)
        o = obj if obj_is_literal else self.graph.resolve_uri(obj)
        if obj_is_literal:
            from rdflib import Literal
            o = Literal(obj)
        self.graph.graph.add((s, p, o))
        fact_id = self.graph.record_fact(
            s, p, o, source=source, confidence=confidence,
            asserted_by=asserted_by, note=note, observed_at=observed_at,
        )
        self.graph.save()
        return fact_id

    def context(self, entity: str, depth: int = 1, limit: int = 50):
        return self.graph.context(entity, depth=depth, limit=limit)

    def context_json(self, entity: str, depth: int = 1, limit: int = 50):
        return json.dumps(self.context(entity, depth=depth, limit=limit), indent=2)


    def batch_links(self, file_path: str):
        import json
        with open(file_path, 'r') as f:
            links = json.load(f)

        for l in links:
            self.graph.add_triple(l['subject'], l['predicate'], l['object'], l.get('literal', False))
        self.graph.save()
        print(f"Batch linked {len(links)} entities successfully.")

    def batch_unlinks(self, file_path: str):
        import json
        with open(file_path, 'r') as f:
            unlinks = json.load(f)

        for u in unlinks:
            self.graph.remove_triple(u['subject'], u['predicate'], u['object'])
        self.graph.save()
        print(f"Batch unlinked {len(unlinks)} entities successfully.")

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
