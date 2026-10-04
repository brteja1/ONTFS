import hashlib
import os
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import SKOS, OWL, RDF, RDFS, XSD
from ontfs.namespaces import bind_namespaces, CUSTOM, ONTFS

DB_FILE = ".ontfs.ttl"
FACT_STATUSES = {"asserted", "verified", "stale", "retracted", "disputed"}

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

        return self.record_fact(s, p, o)

    @staticmethod
    def fact_identifier(s, p, o) -> str:
        """Return a stable identifier for an asserted RDF statement."""
        payload = "\x1f".join((str(s), str(p), str(o))).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:20]

    @staticmethod
    def fact_uri(fact_id):
        return URIRef(str(ONTFS) + "fact/" + fact_id)

    def record_fact(self, s, p, o, source=None, confidence=None,
                    asserted_by=None, note=None, observed_at=None,
                    status="asserted", expires_at=None):
        """Record explainability metadata without changing the asserted triple."""
        if status not in FACT_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(FACT_STATUSES))}")
        fact_id = self.fact_identifier(s, p, o)
        fact = self.fact_uri(fact_id)
        self.graph.add((fact, RDF.type, RDF.Statement))
        self.graph.add((fact, RDF.subject, s))
        self.graph.add((fact, RDF.predicate, p))
        self.graph.add((fact, RDF.object, o))

        if not list(self.graph.objects(fact, ONTFS.status)):
            self.graph.add((fact, ONTFS.status, Literal(status)))

        if source is not None:
            self.graph.add((fact, ONTFS.source, self.resolve_uri(source)))
        if confidence is not None:
            if not 0.0 <= float(confidence) <= 1.0:
                raise ValueError("confidence must be between 0 and 1")
            self.graph.add((fact, ONTFS.confidence, Literal(float(confidence), datatype=XSD.double)))
        if asserted_by is not None:
            self.graph.add((fact, ONTFS.assertedBy, Literal(asserted_by)))
        if note is not None:
            self.graph.add((fact, ONTFS.note, Literal(note)))
        if observed_at is None:
            observed_at = datetime.now(timezone.utc).isoformat()
        self.graph.add((fact, ONTFS.observedAt, Literal(observed_at, datatype=XSD.dateTime)))
        if expires_at is not None:
            self.graph.add((fact, ONTFS.expiresAt, Literal(expires_at, datatype=XSD.dateTime)))
        self.is_dirty = True
        return fact_id

    def remove_triple(self, s_str: str, p_str: str, o_str: str):
        s = self.resolve_uri(s_str)
        p = self.resolve_uri(p_str)
        # Assuming object is URI for unlink command mostly
        o = self.resolve_uri(o_str)
        
        self.graph.remove((s, p, o))
        fact = URIRef(str(ONTFS) + "fact/" + self.fact_identifier(s, p, o))
        for triple in list(self.graph.triples((fact, None, None))):
            self.graph.remove(triple)
        for triple in list(self.graph.triples((None, None, fact))):
            self.graph.remove(triple)
        self.is_dirty = True

    def fact_metadata(self, s, p, o):
        fact = self.fact_uri(self.fact_identifier(s, p, o))
        values = {}
        for predicate, value in self.graph.predicate_objects(fact):
            if predicate in (RDF.type, RDF.subject, RDF.predicate, RDF.object):
                continue
            key = str(predicate).rsplit("#", 1)[-1]
            values[key] = str(value)
        values["id"] = str(fact).rsplit("/", 1)[-1]
        return values

    def fact_record(self, fact_id):
        fact = self.fact_uri(fact_id)
        subject = next(self.graph.objects(fact, RDF.subject), None)
        predicate = next(self.graph.objects(fact, RDF.predicate), None)
        obj = next(self.graph.objects(fact, RDF.object), None)
        if subject is None or predicate is None or obj is None:
            raise ValueError(f"fact not found: {fact_id}")
        metadata = self.fact_metadata(subject, predicate, obj)
        metadata.update({
            "subject": str(subject),
            "predicate": str(predicate),
            "object": str(obj),
        })
        return metadata

    def set_fact_status(self, fact_id, status, reason=None):
        if status not in FACT_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(FACT_STATUSES))}")
        fact = self.fact_uri(fact_id)
        subject = next(self.graph.objects(fact, RDF.subject), None)
        predicate = next(self.graph.objects(fact, RDF.predicate), None)
        obj = next(self.graph.objects(fact, RDF.object), None)
        if subject is None or predicate is None or obj is None:
            raise ValueError(f"fact not found: {fact_id}")
        self.graph.remove((fact, ONTFS.status, None))
        self.graph.add((fact, ONTFS.status, Literal(status)))
        self.graph.remove((fact, ONTFS.statusChangedAt, None))
        self.graph.add((fact, ONTFS.statusChangedAt, Literal(
            datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime
        )))
        if reason is not None:
            self.graph.remove((fact, ONTFS.statusReason, None))
            self.graph.add((fact, ONTFS.statusReason, Literal(reason)))
        if status == "retracted":
            self.graph.remove((subject, predicate, obj))
        self.is_dirty = True
        return self.fact_record(fact_id)

    @staticmethod
    def _parse_datetime(value):
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def refresh_stale(self, now=None):
        now = now or datetime.now(timezone.utc)
        stale = []
        for fact in set(self.graph.subjects(RDF.type, RDF.Statement)):
            expires = next(self.graph.objects(fact, ONTFS.expiresAt), None)
            status = str(next(self.graph.objects(fact, ONTFS.status), "asserted"))
            if expires is None or status not in {"asserted", "verified"}:
                continue
            try:
                expired = self._parse_datetime(expires) <= now
            except ValueError:
                continue
            if expired:
                fact_id = str(fact).rsplit("/", 1)[-1]
                self.set_fact_status(fact_id, "stale", "expiration time reached")
                stale.append(fact_id)
        return stale

    def contradictions(self):
        grouped = {}
        for fact in set(self.graph.subjects(RDF.type, RDF.Statement)):
            subject = next(self.graph.objects(fact, RDF.subject), None)
            predicate = next(self.graph.objects(fact, RDF.predicate), None)
            obj = next(self.graph.objects(fact, RDF.object), None)
            status = str(next(self.graph.objects(fact, ONTFS.status), "asserted"))
            if None in (subject, predicate, obj) or status == "retracted":
                continue
            grouped.setdefault((subject, predicate), []).append((obj, fact, status))
        conflicts = []
        for (subject, predicate), entries in grouped.items():
            objects = {str(entry[0]) for entry in entries}
            if len(objects) > 1:
                conflicts.append({
                    "subject": str(subject),
                    "predicate": str(predicate),
                    "objects": sorted(objects),
                    "facts": [self.fact_record(str(entry[1]).rsplit("/", 1)[-1]) for entry in entries],
                })
        return conflicts

    def context(self, entity: str, depth: int = 1, limit: int = 50):
        """Return bounded, explainable graph context around an entity."""
        if depth < 0:
            raise ValueError("depth must be non-negative")
        if limit <= 0:
            raise ValueError("limit must be positive")
        root = self.resolve_uri(entity)
        frontier = {root}
        visited = {root}
        facts = []
        for _ in range(depth + 1):
            next_frontier = set()
            for s, p, o in self.graph:
                if p in (RDF.type, RDF.subject, RDF.predicate, RDF.object) and (
                    str(s).startswith(str(ONTFS) + "fact/")
                ):
                    continue
                if s not in frontier and o not in frontier:
                    continue
                item = {
                    "subject": str(s),
                    "predicate": str(p),
                    "object": str(o),
                    "fact": self.fact_metadata(s, p, o),
                }
                if item not in facts:
                    facts.append(item)
                if len(facts) >= limit:
                    return {"entity": str(root), "depth": depth, "facts": facts}
                for term in (s, o):
                    if isinstance(term, (URIRef, BNode)) and term not in visited:
                        next_frontier.add(term)
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        return {"entity": str(root), "depth": depth, "facts": facts}

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
