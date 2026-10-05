import hashlib
import os
import urllib.parse
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import SKOS, OWL, RDF, RDFS, XSD, PROV
from ontfs.namespaces import bind_namespaces, CUSTOM, ONTFS
from ontfs.storage import atomic_write, locked

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
        self.graph = Graph()
        bind_namespaces(self.graph)
        if self.db_path.exists():
            self.graph.parse(self.db_path, format="turtle")
        self.is_dirty = False

    def save(self):
        if self.is_dirty:
            atomic_write(self.db_path, self.graph.serialize(format="turtle"))
            self.is_dirty = False

    @contextmanager
    def transaction(self):
        """Reload, mutate, and atomically persist under an exclusive file lock."""
        depth = getattr(self, "_transaction_depth", 0)
        if depth:
            self._transaction_depth = depth + 1
            try:
                yield self
            finally:
                self._transaction_depth -= 1
            return
        with locked(self.db_path):
            self._transaction_depth = 1
            self._load()
            try:
                yield self
                self.save()
            finally:
                self._transaction_depth = 0

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
        uri_str = str(uri_str)
        # Normalize local file URIs into relocatable graph-relative identifiers.
        if uri_str.startswith("file://"):
            parsed = urllib.parse.urlparse(uri_str)
            local_path = Path(urllib.parse.unquote(parsed.path)).resolve()
            try:
                relative = local_path.relative_to(self.directory).as_posix()
                return URIRef(str(ONTFS) + "file/" + urllib.parse.quote(relative, safe="/"))
            except ValueError:
                return URIRef(uri_str)

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
        try:
            relative = abs_path.relative_to(self.directory).as_posix()
            return URIRef(str(ONTFS) + "file/" + urllib.parse.quote(relative, safe="/"))
        except ValueError:
            return URIRef(abs_path.as_uri())

    def to_path(self, uri):
        """Resolve a graph-local file identifier or file URI to an absolute path."""
        uri = str(uri)
        file_prefix = str(ONTFS) + "file/"
        if uri.startswith(file_prefix):
            relative = urllib.parse.unquote(uri[len(file_prefix):])
            return str((self.directory / relative).resolve())
        if uri.startswith("file://"):
            parsed = urllib.parse.urlparse(uri)
            return str(Path(urllib.parse.unquote(parsed.path)).resolve())
        return uri

    def migrate_uris(self):
        """Rewrite local absolute file URIs and reified fact IDs to stable IDs."""
        fact_remap = {}
        term_remap = {}
        for fact in set(self.graph.subjects(RDF.type, RDF.Statement)):
            subject = next(self.graph.objects(fact, RDF.subject), None)
            predicate = next(self.graph.objects(fact, RDF.predicate), None)
            obj = next(self.graph.objects(fact, RDF.object), None)
            if None in (subject, predicate, obj):
                continue
            new_subject = self.resolve_uri(str(subject)) if isinstance(subject, URIRef) else subject
            new_predicate = self.resolve_uri(str(predicate)) if isinstance(predicate, URIRef) else predicate
            new_object = self.resolve_uri(str(obj)) if isinstance(obj, URIRef) else obj
            old_id = str(fact).rsplit("/", 1)[-1]
            new_id = self.fact_identifier(new_subject, new_predicate, new_object)
            new_fact = self.fact_uri(new_id)
            if fact != new_fact:
                fact_remap[old_id] = new_id
                term_remap[fact] = new_fact

        def normalize(term):
            if term in term_remap:
                return term_remap[term]
            if isinstance(term, URIRef):
                return self.resolve_uri(str(term))
            return term

        rewritten = set()
        changed = 0
        for s, p, o in self.graph:
            triple = (normalize(s), normalize(p), normalize(o))
            if triple != (s, p, o):
                changed += 1
            rewritten.add(triple)
        self.graph = Graph()
        bind_namespaces(self.graph)
        for triple in rewritten:
            self.graph.add(triple)
        self.is_dirty = bool(changed)
        return {"triples_changed": changed, "fact_ids": fact_remap}

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

        existing_status = next(self.graph.objects(fact, ONTFS.status), None)
        if existing_status is None:
            self.graph.add((fact, ONTFS.status, Literal(status)))
        elif str(existing_status) == "retracted" and status == "asserted":
            self.graph.remove((fact, ONTFS.status, existing_status))
            self.graph.add((fact, ONTFS.status, Literal(status)))

        evidence_source = self.resolve_uri(source) if source is not None else None
        if confidence is not None:
            if not 0.0 <= float(confidence) <= 1.0:
                raise ValueError("confidence must be between 0 and 1")
        if observed_at is None:
            observed_at = datetime.now(timezone.utc).isoformat()
        if expires_at is not None:
            self.graph.add((fact, ONTFS.expiresAt, Literal(expires_at, datatype=XSD.dateTime)))
        evidence = URIRef(str(ONTFS) + "evidence/" + uuid.uuid4().hex)
        self.graph.add((evidence, RDF.type, ONTFS.Evidence))
        self.graph.add((evidence, ONTFS.supports, fact))
        if evidence_source is not None:
            self.graph.add((evidence, PROV.wasDerivedFrom, evidence_source))
        if confidence is not None:
            self.graph.add((evidence, ONTFS.confidence, Literal(float(confidence), datatype=XSD.double)))
        if asserted_by is not None:
            self.graph.add((evidence, PROV.wasAttributedTo, Literal(asserted_by)))
        if note is not None:
            self.graph.add((evidence, ONTFS.note, Literal(note)))
        self.graph.add((evidence, PROV.generatedAtTime, Literal(observed_at, datatype=XSD.dateTime)))
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
            if predicate in (ONTFS.status, ONTFS.expiresAt, ONTFS.statusChangedAt,
                             ONTFS.statusReason):
                values[key] = str(value)
            elif predicate in (ONTFS.source, ONTFS.confidence, ONTFS.assertedBy,
                               ONTFS.note, ONTFS.observedAt):
                values[key] = self.to_path(value) if key == "source" else str(value)
        evidence_records = []
        confidences = []
        for evidence in self.graph.subjects(ONTFS.supports, fact):
            record = {"id": str(evidence).rsplit("/", 1)[-1]}
            source = next(self.graph.objects(evidence, PROV.wasDerivedFrom), None)
            agent = next(self.graph.objects(evidence, PROV.wasAttributedTo), None)
            timestamp = next(self.graph.objects(evidence, PROV.generatedAtTime), None)
            confidence = next(self.graph.objects(evidence, ONTFS.confidence), None)
            note = next(self.graph.objects(evidence, ONTFS.note), None)
            if source is not None:
                record["source"] = self.to_path(source)
            if agent is not None:
                record["assertedBy"] = str(agent)
            if timestamp is not None:
                record["observedAt"] = str(timestamp)
            if confidence is not None:
                record["confidence"] = float(confidence)
                confidences.append(float(confidence))
            if note is not None:
                record["note"] = str(note)
            evidence_records.append(record)
        values["evidence"] = evidence_records[:50]
        values["evidenceCount"] = len(evidence_records)
        if evidence_records:
            latest = evidence_records[-1]
            for key in ("source", "assertedBy", "note", "observedAt"):
                if key in latest:
                    values[key] = latest[key]
        values["statusHistory"] = [
            {
                "from": str(next(self.graph.objects(event, ONTFS.fromStatus), "")),
                "to": str(next(self.graph.objects(event, ONTFS.toStatus), "")),
                "at": str(next(self.graph.objects(event, PROV.generatedAtTime), "")),
                "note": str(next(self.graph.objects(event, ONTFS.note), "")),
            }
            for event in self.graph.objects(fact, ONTFS.statusEvent)
        ]
        if confidences:
            values["confidence"] = max(confidences)
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
            "subject": self.to_path(subject),
            "predicate": str(predicate),
            "object": self.to_path(obj),
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
        old_status = str(next(self.graph.objects(fact, ONTFS.status), "asserted"))
        self.graph.remove((fact, ONTFS.status, None))
        self.graph.add((fact, ONTFS.status, Literal(status)))
        self.graph.remove((fact, ONTFS.statusChangedAt, None))
        self.graph.add((fact, ONTFS.statusChangedAt, Literal(
            datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime
        )))
        if reason is not None:
            self.graph.remove((fact, ONTFS.statusReason, None))
            self.graph.add((fact, ONTFS.statusReason, Literal(reason)))
        event = URIRef(str(ONTFS) + "statusEvent/" + uuid.uuid4().hex)
        self.graph.add((fact, ONTFS.statusEvent, event))
        self.graph.add((event, RDF.type, ONTFS.StatusEvent))
        self.graph.add((event, ONTFS.fromStatus, Literal(old_status)))
        self.graph.add((event, ONTFS.toStatus, Literal(status)))
        self.graph.add((event, PROV.generatedAtTime, Literal(
            datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime
        )))
        if reason:
            self.graph.add((event, ONTFS.note, Literal(reason)))
        if status == "retracted":
            self.graph.remove((subject, predicate, obj))
        self.is_dirty = True
        return self.fact_record(fact_id)

    def migrate_evidence(self):
        """Move legacy per-fact evidence metadata into a single evidence record."""
        legacy = (
            (ONTFS.source, "source"), (ONTFS.confidence, "confidence"),
            (ONTFS.assertedBy, "agent"), (ONTFS.note, "note"),
            (ONTFS.observedAt, "time"),
        )
        migrated = 0
        for fact in set(self.graph.subjects(RDF.type, RDF.Statement)):
            if next(self.graph.subjects(ONTFS.supports, fact), None) is not None:
                continue
            if not any(list(self.graph.objects(fact, predicate)) for predicate, _ in legacy):
                continue
            evidence = URIRef(str(ONTFS) + "evidence/" + uuid.uuid4().hex)
            self.graph.add((evidence, RDF.type, ONTFS.Evidence))
            self.graph.add((evidence, ONTFS.supports, fact))
            for predicate, kind in legacy:
                for value in list(self.graph.objects(fact, predicate)):
                    if kind == "source":
                        self.graph.add((evidence, PROV.wasDerivedFrom, value))
                    elif kind == "agent":
                        self.graph.add((evidence, PROV.wasAttributedTo, value))
                    elif kind == "time":
                        self.graph.add((evidence, PROV.generatedAtTime, value))
                    else:
                        self.graph.add((evidence, predicate, value))
                    self.graph.remove((fact, predicate, value))
            migrated += 1
        self.is_dirty = self.is_dirty or migrated > 0
        return migrated

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
        try:
            from ontfs.validation import functional_paths, load_shapes
            shapes, _ = load_shapes(self.directory)
            shacl_functional = functional_paths(shapes)
        except Exception:
            shacl_functional = set()
        for fact in set(self.graph.subjects(RDF.type, RDF.Statement)):
            subject = next(self.graph.objects(fact, RDF.subject), None)
            predicate = next(self.graph.objects(fact, RDF.predicate), None)
            obj = next(self.graph.objects(fact, RDF.object), None)
            status = str(next(self.graph.objects(fact, ONTFS.status), "asserted"))
            if None in (subject, predicate, obj) or status == "retracted":
                continue
            if ((predicate, RDF.type, OWL.FunctionalProperty) not in self.graph
                    and predicate not in shacl_functional):
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

    def entity_status(self, entity):
        node = self.resolve_uri(entity)
        value = next(self.graph.objects(node, ONTFS.entityStatus), None)
        return str(value) if value is not None else None

    def context(self, entity: str, depth: int = 1, limit: int = 50,
                include_superseded: bool = False):
        """Return bounded, explainable graph context around an entity."""
        if depth < 0:
            raise ValueError("depth must be non-negative")
        if limit <= 0:
            raise ValueError("limit must be positive")
        root = self.resolve_uri(entity)
        root_status = self.entity_status(root)
        frontier = {root}
        visited = {root}
        facts = []
        for _ in range(depth + 1):
            next_frontier = set()
            adjacent = set()
            for node in frontier:
                adjacent.update(self.graph.triples((node, None, None)))
                adjacent.update(self.graph.triples((None, None, node)))
            for s, p, o in sorted(adjacent, key=lambda triple: tuple(map(str, triple))):
                if p in (ONTFS.entityStatus, ONTFS.supersedes, ONTFS.supersededBy):
                    continue
                if p in (RDF.type, RDF.subject, RDF.predicate, RDF.object) and (
                    str(s).startswith(str(ONTFS) + "fact/")
                ):
                    continue
                if s not in frontier and o not in frontier:
                    continue
                statuses = {
                    term: self.entity_status(term)
                    for term in (s, o)
                    if isinstance(term, URIRef) and term != root
                }
                if not include_superseded and "superseded" in statuses.values():
                    continue
                item = {
                    "subject": self.to_path(s),
                    "predicate": str(p),
                    "object": self.to_path(o),
                    "fact": self.fact_metadata(s, p, o),
                }
                if item not in facts:
                    facts.append(item)
                if len(facts) >= limit:
                    return {
                        "entity": self.to_path(root), "depth": depth,
                        "entity_status": str(root_status) if root_status else None,
                        "facts": facts,
                    }
                for term in (s, o):
                    if isinstance(term, (URIRef, BNode)) and term not in visited:
                        next_frontier.add(term)
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        return {
            "entity": self.to_path(root), "depth": depth,
            "entity_status": str(root_status) if root_status else None,
            "facts": facts,
        }

    def define_relation(self, uri_str: str, rel_type: str = None, 
                        is_transitive: bool = False, is_symmetric: bool = False,
                        subprop_of: str = None, inverse_of: str = None,
                        functional: bool = False):
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
        if functional:
            self.graph.add((p, RDF.type, OWL.FunctionalProperty))
            
        if subprop_of:
            self.graph.add((p, RDFS.subPropertyOf, self.resolve_uri(subprop_of)))
            
        if inverse_of:
            self.graph.add((p, OWL.inverseOf, self.resolve_uri(inverse_of)))
            
        self.is_dirty = True

    def query_graph(self, query_str: str):
        """Execute a SPARQL query"""
        return self.graph.query(query_str)
