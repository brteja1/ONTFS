import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from rdflib import Literal, RDF
from ontfs.rdf_handler import OntFSGraph
from ontfs.namespaces import ONTFS
from ontfs.storage import atomic_write, locked


def graph_transaction(method):
    def wrapped(self, *args, **kwargs):
        with self.graph.transaction():
            return method(self, *args, **kwargs)
    wrapped.__name__ = method.__name__
    wrapped.__doc__ = method.__doc__
    return wrapped


def proposal_transaction(method):
    def wrapped(self, *args, **kwargs):
        with locked(self.proposals_path):
            return method(self, *args, **kwargs)
    wrapped.__name__ = method.__name__
    wrapped.__doc__ = method.__doc__
    return wrapped

class OntFS:
    PROPOSALS_FILE = ".ontfs.proposals.json"

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
            
    @graph_transaction
    def add_relation(self, uri: str, rel_type: str = None, 
                     is_transitive: bool = False, is_symmetric: bool = False,
                     subprop_of: str = None, inverse_of: str = None,
                     functional: bool = False):
        self.graph.define_relation(
            uri_str=uri,
            rel_type=rel_type,
            is_transitive=is_transitive,
            is_symmetric=is_symmetric,
            subprop_of=subprop_of,
            inverse_of=inverse_of, functional=functional
        )
        self.graph.save()
        print(f"Relation {uri} defined successfully.")


    @graph_transaction
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
                inverse_of=rel.get('inverse') or rel.get('inverse_of'),
                functional=rel.get('functional', False)
            )
        self.graph.save()
        print(f"Batch defined {len(relations)} relations successfully.")

    @graph_transaction
    def link(self, subject: str, predicate: str, obj: str, obj_is_literal: bool = False):
        fact_id = self.graph.add_triple(subject, predicate, obj, obj_is_literal)
        self.graph.save()
        print(f"Linked: {subject} -[{predicate}]-> {obj}")
        return fact_id

    @graph_transaction
    def remember(self, subject: str, predicate: str, obj: str,
                 obj_is_literal: bool = False, source: str = None,
                 confidence: float = None, asserted_by: str = None,
                 note: str = None, observed_at: str = None,
                 status: str = "asserted", expires_at: str = None):
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
            status=status, expires_at=expires_at,
        )
        self.graph.save()
        return fact_id

    def context(self, entity: str, depth: int = 1, limit: int = 50,
                include_superseded: bool = False):
        return self.graph.context(
            entity, depth=depth, limit=limit,
            include_superseded=include_superseded,
        )

    def context_json(self, entity: str, depth: int = 1, limit: int = 50):
        return json.dumps(self.context(entity, depth=depth, limit=limit), indent=2)

    @graph_transaction
    def set_entity_status(self, entity, status, reason=None):
        return self._set_entity_status(entity, status, reason)

    def _set_entity_status(self, entity, status, reason=None):
        allowed = {"active", "verified", "experimental", "stale", "superseded", "deprecated"}
        if status not in allowed:
            raise ValueError(f"entity status must be one of: {', '.join(sorted(allowed))}")
        node = self.graph.resolve_uri(entity)
        self.graph.define_relation("ontfs:entityStatus", rel_type="datatype", functional=True)
        for old in list(self.graph.graph.objects(node, ONTFS.entityStatus)):
            if str(old) == status:
                return str(old)
            old_fact = self.graph.fact_identifier(node, ONTFS.entityStatus, old)
            if (self.graph.fact_uri(old_fact), RDF.type, RDF.Statement) in self.graph.graph:
                self.graph.set_fact_status(old_fact, "retracted", "entity status changed")
            else:
                self.graph.graph.remove((node, ONTFS.entityStatus, old))
        literal = Literal(status)
        self.graph.graph.add((node, ONTFS.entityStatus, literal))
        self.graph.record_fact(
            node, ONTFS.entityStatus, literal,
            asserted_by="ontfs", note=reason,
        )
        return status

    @graph_transaction
    def supersede(self, new_entity, old_entity, source=None, note=None):
        self.graph.define_relation("ontfs:supersedes", rel_type="object", inverse_of="ontfs:supersededBy")
        self.graph.define_relation("ontfs:supersededBy", rel_type="object", inverse_of="ontfs:supersedes")
        self.graph.add_triple(new_entity, "ontfs:supersedes", old_entity)
        new_node = self.graph.resolve_uri(new_entity)
        old_node = self.graph.resolve_uri(old_entity)
        relationship_fact = self.graph.fact_identifier(
            new_node, self.graph.resolve_uri("ontfs:supersedes"), old_node
        )
        fact = self.graph.fact_uri(relationship_fact)
        if source is not None:
            self.graph.graph.add((fact, ONTFS.source, self.graph.resolve_uri(source)))
        if note is not None:
            self.graph.graph.add((fact, ONTFS.note, Literal(note)))
        self._set_entity_status(old_entity, "superseded", f"superseded by {new_entity}")
        return relationship_fact

    @proposal_transaction
    @graph_transaction
    def migrate_uris(self, dry_run=False):
        """Convert local absolute file URIs and update proposal fact references."""
        result = self.graph.migrate_uris()
        if dry_run:
            # transaction must not persist the in-memory preview
            self.graph._load()
            return result
        fact_remap = result["fact_ids"]
        if fact_remap and self.proposals_path.exists():
            proposals = self._load_proposals()
            for proposal in proposals:
                if proposal.get("fact_id") in fact_remap:
                    proposal["fact_id"] = fact_remap[proposal["fact_id"]]
                for event in proposal.get("history", []):
                    if event.get("fact_id") in fact_remap:
                        event["fact_id"] = fact_remap[event["fact_id"]]
            self._save_proposals(proposals)
        return result

    @graph_transaction
    def migrate_evidence(self):
        return self.graph.migrate_evidence()

    def search(self, query, path=".", limit=20, related_to=None, depth=1,
               vector=False, embedding_dimensions=256, embedding_backend="hashed",
               embedding_model=None):
        from ontfs.search import search
        return search(
            self, query, path=path, limit=limit,
            related_to=related_to, depth=depth, vector=vector,
            embedding_dimensions=embedding_dimensions,
            embedding_backend=embedding_backend, embedding_model=embedding_model,
        )

    def select(self, expression, predicate="ontfs:hasTag", limit=100):
        from ontfs.select import select
        return select(self, expression, predicate=predicate, limit=limit)

    def recall(self, query, limit=6, summary_predicate="dcterms:abstract",
               search_text=True, vector=False, max_tokens=1200):
        from ontfs.recall import recall
        return recall(self, query, limit=limit, summary_predicate=summary_predicate,
                      search_text=search_text, vector=vector, max_tokens=max_tokens)

    def fact(self, fact_id):
        return self.graph.fact_record(fact_id)

    @graph_transaction
    def set_fact_status(self, fact_id, status, reason=None):
        record = self.graph.set_fact_status(fact_id, status, reason=reason)
        self.graph.save()
        return record

    @graph_transaction
    def refresh_stale(self):
        stale = self.graph.refresh_stale()
        self.graph.save()
        return stale

    def contradictions(self, mark=False):
        if mark:
            return self._mark_contradictions()
        return self.graph.contradictions()

    @graph_transaction
    def _mark_contradictions(self):
        conflicts = self.graph.contradictions()
        for conflict in conflicts:
            for fact in conflict["facts"]:
                self.graph.set_fact_status(
                    fact["id"], "disputed", "conflicting object for subject and predicate"
                )
        return conflicts

    @graph_transaction
    def scan(self, path=".", include_git=True):
        from ontfs.scanner import scan
        return scan(self, path=path, include_git=include_git)

    def watch(self, path=".", interval=1.0, iterations=None, include_git=True):
        from ontfs.watcher import watch
        return watch(
            self, path=path, interval=interval,
            iterations=iterations, include_git=include_git,
        )

    @property
    def proposals_path(self):
        return self.directory / self.PROPOSALS_FILE

    def _load_proposals(self):
        if not self.proposals_path.exists():
            return []
        with locked(self.proposals_path):
            with self.proposals_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        if not isinstance(data, list):
            raise ValueError(f"{self.PROPOSALS_FILE} must contain a JSON array")
        return data

    def _save_proposals(self, proposals):
        atomic_write(self.proposals_path, json.dumps(proposals, indent=2) + "\n")

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @proposal_transaction
    def propose_link(self, subject: str, predicate: str, obj: str,
                     obj_is_literal: bool = False, source: str = None,
                     confidence: float = None, asserted_by: str = None,
                     note: str = None, observed_at: str = None,
                     expires_at: str = None):
        """Create a pending link proposal without changing the RDF graph."""
        proposal = {
            "id": uuid.uuid4().hex[:16],
            "operation": "link",
            "status": "proposed",
            "created_at": self._now(),
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "literal": obj_is_literal,
            "source": source,
            "confidence": confidence,
            "asserted_by": asserted_by,
            "note": note,
            "observed_at": observed_at,
            "expires_at": expires_at,
            "history": [{"event": "proposed", "at": self._now()}],
        }
        self._validate_proposal(proposal)
        proposals = self._load_proposals()
        proposals.append(proposal)
        self._save_proposals(proposals)
        return proposal

    def _validate_proposal(self, proposal):
        required = ("subject", "predicate", "object")
        errors = [f"missing {field}" for field in required if not proposal.get(field)]
        confidence = proposal.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
                if not 0.0 <= confidence <= 1.0:
                    errors.append("confidence must be between 0 and 1")
            except (TypeError, ValueError):
                errors.append("confidence must be a number between 0 and 1")
        if proposal.get("operation") != "link":
            errors.append("unsupported operation")
        if errors:
            raise ValueError("; ".join(errors))
        # URI resolution is also a useful validation step for unknown prefixes.
        self.graph.resolve_uri(proposal["subject"])
        self.graph.resolve_uri(proposal["predicate"])
        if not proposal.get("literal"):
            self.graph.resolve_uri(proposal["object"])
        return True

    def list_proposals(self, status=None):
        proposals = self._load_proposals()
        if status is not None:
            proposals = [p for p in proposals if p.get("status") == status]
        return proposals

    def validate_proposal(self, proposal_id):
        from collections import Counter

        proposal = self._find_proposal(proposal_id)
        try:
            self._validate_proposal(proposal)
        except ValueError as error:
            return {"id": proposal_id, "valid": False, "error": str(error)}
        from ontfs.validation import load_shapes, validate_graph
        shapes, _ = load_shapes(self.directory)
        if shapes is not None:
            try:
                baseline = validate_graph(self.graph.graph, self.directory)
            except RuntimeError as error:
                return {"id": proposal_id, "valid": False, "error": str(error)}
            candidate = self.graph.graph.__class__()
            for prefix, namespace in self.graph.graph.namespaces():
                candidate.bind(prefix, namespace, replace=True)
            for triple in self.graph.graph:
                candidate.add(triple)
            subject = self.graph.resolve_uri(proposal["subject"])
            predicate = self.graph.resolve_uri(proposal["predicate"])
            if proposal.get("literal"):
                from rdflib import Literal
                obj = Literal(proposal["object"])
            else:
                obj = self.graph.resolve_uri(proposal["object"])
            candidate.add((subject, predicate, obj))
            try:
                validation = validate_graph(candidate, self.directory)
            except RuntimeError as error:
                return {"id": proposal_id, "valid": False, "error": str(error)}
            def violation_key(item):
                # Messages are presentation text: prefixes and list ordering
                # may change without changing the underlying violation.
                return (
                    item["focus_node"], item["path"],
                    item["source_constraint"], item["source_shape"],
                    item["value"], item["value_count"],
                )

            baseline_violations = Counter(
                violation_key(item) for item in baseline["violations"]
            )
            candidate_violations = Counter(
                violation_key(item) for item in validation["violations"]
            )
            new_violations = []
            for item in validation["violations"]:
                key = violation_key(item)
                if candidate_violations[key] > baseline_violations[key]:
                    new_violations.append(item)
                    candidate_violations[key] -= 1
            if new_violations:
                return {
                    "id": proposal_id, "valid": False,
                    "violations": new_violations,
                }
        return {"id": proposal_id, "valid": True, "status": proposal["status"]}

    def validate(self, shapes_path=None):
        from ontfs.validation import validate_graph
        return validate_graph(self.graph.graph, self.directory, shapes_path)

    def _find_proposal(self, proposal_id):
        for proposal in self._load_proposals():
            if proposal.get("id") == proposal_id:
                return proposal
        raise ValueError(f"proposal not found: {proposal_id}")

    def _update_proposal(self, proposal):
        proposals = self._load_proposals()
        for index, current in enumerate(proposals):
            if current.get("id") == proposal.get("id"):
                proposals[index] = proposal
                self._save_proposals(proposals)
                return
        raise ValueError(f"proposal not found: {proposal.get('id')}")

    @proposal_transaction
    @graph_transaction
    def commit_proposal(self, proposal_id):
        proposal = self._find_proposal(proposal_id)
        if proposal.get("status") != "proposed":
            raise ValueError(f"proposal is already {proposal.get('status')}")
        validation = self.validate_proposal(proposal_id)
        if not validation.get("valid"):
            raise ValueError(json.dumps(validation, sort_keys=True))
        fact_id = self.remember(
            proposal["subject"], proposal["predicate"], proposal["object"],
            obj_is_literal=proposal.get("literal", False),
            source=proposal.get("source"), confidence=proposal.get("confidence"),
            asserted_by=proposal.get("asserted_by"), note=proposal.get("note"),
            observed_at=proposal.get("observed_at"), expires_at=proposal.get("expires_at"),
        )
        proposal["status"] = "committed"
        proposal["fact_id"] = fact_id
        proposal["committed_at"] = self._now()
        proposal.setdefault("history", []).append({
            "event": "committed", "at": proposal["committed_at"], "fact_id": fact_id,
        })
        self._update_proposal(proposal)
        return proposal

    @proposal_transaction
    def reject_proposal(self, proposal_id, reason=None):
        proposal = self._find_proposal(proposal_id)
        if proposal.get("status") != "proposed":
            raise ValueError(f"proposal is already {proposal.get('status')}")
        proposal["status"] = "rejected"
        proposal["rejected_at"] = self._now()
        if reason:
            proposal["rejection_reason"] = reason
        proposal.setdefault("history", []).append({
            "event": "rejected", "at": proposal["rejected_at"], "reason": reason,
        })
        self._update_proposal(proposal)
        return proposal


    @graph_transaction
    def batch_links(self, file_path: str):
        import json
        with open(file_path, 'r') as f:
            links = json.load(f)

        for l in links:
            self.graph.add_triple(l['subject'], l['predicate'], l['object'], l.get('literal', False))
        self.graph.save()
        print(f"Batch linked {len(links)} entities successfully.")

    @graph_transaction
    def batch_unlinks(self, file_path: str):
        import json
        with open(file_path, 'r') as f:
            unlinks = json.load(f)

        for u in unlinks:
            self.graph.remove_triple(u['subject'], u['predicate'], u['object'])
        self.graph.save()
        print(f"Batch unlinked {len(unlinks)} entities successfully.")

    @graph_transaction
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
