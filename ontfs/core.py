import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from ontfs.rdf_handler import OntFSGraph

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

    def context(self, entity: str, depth: int = 1, limit: int = 50):
        return self.graph.context(entity, depth=depth, limit=limit)

    def context_json(self, entity: str, depth: int = 1, limit: int = 50):
        return json.dumps(self.context(entity, depth=depth, limit=limit), indent=2)

    def search(self, query, path=".", limit=20, related_to=None, depth=1):
        from ontfs.search import search
        return search(
            self, query, path=path, limit=limit,
            related_to=related_to, depth=depth,
        )

    def fact(self, fact_id):
        return self.graph.fact_record(fact_id)

    def set_fact_status(self, fact_id, status, reason=None):
        record = self.graph.set_fact_status(fact_id, status, reason=reason)
        self.graph.save()
        return record

    def refresh_stale(self):
        stale = self.graph.refresh_stale()
        self.graph.save()
        return stale

    def contradictions(self, mark=False):
        conflicts = self.graph.contradictions()
        if mark:
            for conflict in conflicts:
                for fact in conflict["facts"]:
                    self.graph.set_fact_status(
                        fact["id"], "disputed", "conflicting object for subject and predicate"
                    )
            self.graph.save()
        return conflicts

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
        with self.proposals_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            raise ValueError(f"{self.PROPOSALS_FILE} must contain a JSON array")
        return data

    def _save_proposals(self, proposals):
        with self.proposals_path.open("w", encoding="utf-8") as handle:
            json.dump(proposals, handle, indent=2)
            handle.write("\n")

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

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
        proposal = self._find_proposal(proposal_id)
        try:
            self._validate_proposal(proposal)
        except ValueError as error:
            return {"id": proposal_id, "valid": False, "error": str(error)}
        return {"id": proposal_id, "valid": True, "status": proposal["status"]}

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

    def commit_proposal(self, proposal_id):
        proposal = self._find_proposal(proposal_id)
        if proposal.get("status") != "proposed":
            raise ValueError(f"proposal is already {proposal.get('status')}")
        self._validate_proposal(proposal)
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
