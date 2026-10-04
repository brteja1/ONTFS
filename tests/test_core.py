import os
import tempfile
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path
from ontfs.core import OntFS

class TestOntFSCore(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for each test
        self.test_dir = tempfile.TemporaryDirectory()
        self.ontfs = OntFS(directory=self.test_dir.name)
        self.ontfs.init()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_init_creates_file(self):
        db_path = Path(self.test_dir.name) / ".ontfs.ttl"
        self.assertTrue(db_path.exists())

    def test_add_relation_and_link(self):
        # Define a relation
        rel = "custom:dependsOn"
        self.ontfs.add_relation(rel, rel_type="object", is_transitive=True)

        # Link two local files
        self.ontfs.link("./file_a.txt", rel, "./file_b.txt")
        
        # Query to verify the link
        query = f"""
        PREFIX custom: <http://ontfs.example.org/custom#>
        SELECT ?obj WHERE {{
            <file://{Path(self.test_dir.name).resolve()}/file_a.txt> custom:dependsOn ?obj .
        }}
        """
        results = list(self.ontfs.graph.query_graph(query))
        self.assertEqual(len(results), 1)
        
        # Check that the object resolved properly to an absolute file URI
        expected_obj = f"file://{Path(self.test_dir.name).resolve()}/file_b.txt"
        self.assertEqual(str(results[0][0]), expected_obj)

    def test_unlink(self):
        rel = "custom:references"
        self.ontfs.link("./doc1.md", rel, "https://example.com")
        
        # Verify it exists
        query = f"SELECT ?o WHERE {{ ?s <http://ontfs.example.org/custom#references> ?o }}"
        results_before = list(self.ontfs.graph.query_graph(query))
        self.assertEqual(len(results_before), 1)
        
        # Unlink
        self.ontfs.unlink("./doc1.md", rel, "https://example.com")
        
        # Verify it's gone
        results_after = list(self.ontfs.graph.query_graph(query))
        self.assertEqual(len(results_after), 0)

    def test_transitive_query(self):
        # This tests SPARQL evaluation of transitive property paths
        rel = "custom:isChildOf"
        # Even without defining it as owl:TransitiveProperty in the graph, 
        # SPARQL property paths (*) can traverse it.
        self.ontfs.link("custom:tag:Grandchild", rel, "custom:tag:Child")
        self.ontfs.link("custom:tag:Child", rel, "custom:tag:Parent")
        
        # Query all ancestors of Grandchild
        query = f"""
        PREFIX custom: <http://ontfs.example.org/custom#>
        SELECT ?ancestor WHERE {{
            <http://ontfs.example.org/custom#tag:Grandchild> custom:isChildOf+ ?ancestor .
        }}
        """
        results = list(self.ontfs.graph.query_graph(query))
        ancestors = {str(row[0]) for row in results}
        
        expected = {
            "http://ontfs.example.org/custom#tag:Child",
            "http://ontfs.example.org/custom#tag:Parent"
        }
        self.assertEqual(ancestors, expected)

    def test_remember_records_provenance_and_context(self):
        fact_id = self.ontfs.remember(
            "./service.py", "custom:dependsOn", "./database.py",
            source="./architecture.md", confidence=0.9,
            asserted_by="build-agent", note="Found in architecture document",
        )
        self.assertEqual(len(fact_id), 20)

        context = self.ontfs.context("./service.py", depth=1)
        self.assertEqual(len(context["facts"]), 1)
        fact = context["facts"][0]
        self.assertEqual(fact["fact"]["id"], fact_id)
        self.assertEqual(fact["fact"]["confidence"], "0.9")
        self.assertEqual(fact["fact"]["assertedBy"], "build-agent")
        self.assertTrue(fact["fact"]["source"].endswith("/architecture.md"))

        # Metadata survives a reload from the portable Turtle file.
        reloaded = OntFS(directory=self.test_dir.name)
        context_json = reloaded.context_json("./service.py")
        self.assertEqual(json.loads(context_json)["facts"][0]["fact"]["id"], fact_id)

    def test_confidence_must_be_in_range(self):
        with self.assertRaises(ValueError):
            self.ontfs.remember("a", "custom:rel", "b", confidence=1.1)

    def test_proposal_requires_commit_and_keeps_audit_history(self):
        proposal = self.ontfs.propose_link(
            "./service.py", "custom:dependsOn", "./database.py",
            source="./architecture.md", confidence=0.8,
            asserted_by="review-agent",
        )
        self.assertEqual(proposal["status"], "proposed")
        self.assertEqual(list(self.ontfs.graph.graph.triples((None, None, None))), [])
        self.assertEqual(self.ontfs.validate_proposal(proposal["id"])["valid"], True)

        committed = self.ontfs.commit_proposal(proposal["id"])
        self.assertEqual(committed["status"], "committed")
        self.assertTrue(committed["fact_id"])
        self.assertEqual(len(self.ontfs.context("./service.py")["facts"]), 1)
        self.assertEqual(len(committed["history"]), 2)

        rejected = self.ontfs.propose_link("./a", "custom:rel", "./b")
        rejected = self.ontfs.reject_proposal(rejected["id"], "Not supported by evidence")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["rejection_reason"], "Not supported by evidence")

    def test_scan_indexes_python_imports_and_git_context(self):
        Path(self.test_dir.name, "main.py").write_text(
            "import os\nfrom pkg.helpers import run\n", encoding="utf-8"
        )
        Path(self.test_dir.name, "pkg.py").write_text("VALUE = 1\n", encoding="utf-8")
        git = {"root": self.test_dir.name, "commit": "abc123", "branch": "main"}
        with patch("ontfs.scanner._git_info", return_value=git):
            result = self.ontfs.scan()

        self.assertEqual(result["scanned"], 2)
        self.assertEqual(result["imports"], 2)
        self.assertEqual(result["git"]["commit"], "abc123")
        predicates = {
            item["predicate"] for item in self.ontfs.context("./main.py")["facts"]
        }
        self.assertIn("http://ontfs.example.org/custom#imports", predicates)
        self.assertIn("http://ontfs.example.org/custom#gitCommit", predicates)

    def test_watch_rescans_when_snapshot_changes(self):
        Path(self.test_dir.name, "main.py").write_text("import os\n", encoding="utf-8")
        with patch(
            "ontfs.watcher.snapshot",
            side_effect=[{"before": (1, 1)}, {"after": (2, 2)}],
        ), patch(
            "ontfs.watcher.scan",
            side_effect=[{"scanned": 1}, {"scanned": 2}],
        ) as scanner:
            results = self.ontfs.watch(interval=0, iterations=1)
        self.assertEqual(results, [{"scanned": 1}, {"scanned": 2}])
        self.assertEqual(scanner.call_count, 2)

    def test_watch_rejects_invalid_interval(self):
        with self.assertRaises(ValueError):
            self.ontfs.watch(interval=-1, iterations=0)

    def test_fact_lifecycle_staleness_retraction_and_contradictions(self):
        expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        stale_id = self.ontfs.remember(
            "./service.py", "custom:expires", "./old-config.py", expires_at=expired
        )
        self.assertEqual(self.ontfs.refresh_stale(), [stale_id])
        self.assertEqual(self.ontfs.fact(stale_id)["status"], "stale")

        retract_id = self.ontfs.remember("./old.py", "custom:status", "obsolete")
        self.ontfs.set_fact_status(retract_id, "retracted", "superseded")
        self.assertEqual(self.ontfs.fact(retract_id)["status"], "retracted")
        self.assertEqual(self.ontfs.context("./old.py")["facts"], [])

        first = self.ontfs.remember(
            "./service.py", "custom:owner", "team-a", obj_is_literal=True
        )
        second = self.ontfs.remember(
            "./service.py", "custom:owner", "team-b", obj_is_literal=True
        )
        conflicts = self.ontfs.contradictions(mark=True)
        owner_conflict = next(c for c in conflicts if c["predicate"].endswith("#owner"))
        self.assertEqual(set(owner_conflict["objects"]), {"team-a", "team-b"})
        self.assertEqual(self.ontfs.fact(first)["status"], "disputed")
        self.assertEqual(self.ontfs.fact(second)["status"], "disputed")


    def test_batch_relations(self):
        import json
        batch_file = Path(self.test_dir.name) / "relations.json"
        with open(batch_file, "w") as f:
            json.dump([
                {"uri": "custom:isRelatedTo", "type": "object", "symmetric": True},
                {"uri": "custom:isFriendOf", "subprop_of": "custom:isRelatedTo"}
            ], f)

        self.ontfs.add_relations(str(batch_file))

        # Verify relations are added
        query = f"SELECT ?p ?o WHERE {{ ?p a <http://www.w3.org/2002/07/owl#ObjectProperty> }}"
        results = list(self.ontfs.graph.query_graph(query))
        self.assertTrue(len(results) > 0)

    def test_batch_links_and_unlinks(self):
        import json
        rel = "custom:dependsOn"

        links_file = Path(self.test_dir.name) / "links.json"
        with open(links_file, "w") as f:
            json.dump([
                {"subject": "./file1.txt", "predicate": rel, "object": "./file2.txt"},
                {"subject": "./file2.txt", "predicate": rel, "object": "./file3.txt"}
            ], f)

        self.ontfs.batch_links(str(links_file))

        query = f"SELECT ?o WHERE {{ ?s <http://ontfs.example.org/custom#dependsOn> ?o }}"
        results = list(self.ontfs.graph.query_graph(query))
        self.assertEqual(len(results), 2)

        unlinks_file = Path(self.test_dir.name) / "unlinks.json"
        with open(unlinks_file, "w") as f:
            json.dump([
                {"subject": "./file1.txt", "predicate": rel, "object": "./file2.txt"}
            ], f)

        self.ontfs.batch_unlinks(str(unlinks_file))

        results_after = list(self.ontfs.graph.query_graph(query))
        self.assertEqual(len(results_after), 1)

if __name__ == "__main__":
    unittest.main()
