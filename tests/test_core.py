import os
import tempfile
import json
import unittest
import subprocess
import sys
import importlib.util
import shutil
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path
from ontfs.core import OntFS
from ontfs.storage import atomic_write

try:
    from ontfs.mcp_server import create_server
except ImportError:
    create_server = None

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
            <{self.ontfs.graph.resolve_uri('./file_a.txt')}> custom:dependsOn ?obj .
        }}
        """
        results = list(self.ontfs.graph.query_graph(query))
        self.assertEqual(len(results), 1)
        
        # Check that the object resolved properly to an absolute file URI
        expected_obj = str(self.ontfs.graph.resolve_uri("./file_b.txt"))
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
        self.assertAlmostEqual(fact["fact"]["confidence"], 0.9)
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
            "ontfs.watcher.evict_files",
        ), patch.object(
            self.ontfs,
            "scan",
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
        self.ontfs.add_relation("custom:owner", functional=True)
        conflicts = self.ontfs.contradictions(mark=True)
        owner_conflict = next(c for c in conflicts if c["predicate"].endswith("#owner"))
        self.assertEqual(set(owner_conflict["objects"]), {"team-a", "team-b"})
        self.assertEqual(self.ontfs.fact(first)["status"], "disputed")
        self.assertEqual(self.ontfs.fact(second)["status"], "disputed")

    def test_only_functional_properties_report_conflicts(self):
        self.ontfs.remember("a", "custom:many", "one", obj_is_literal=True)
        self.ontfs.remember("a", "custom:many", "two", obj_is_literal=True)
        self.assertEqual(self.ontfs.contradictions(), [])
        self.ontfs.add_relation("custom:one", functional=True)
        self.ontfs.remember("a", "custom:one", "one", obj_is_literal=True)
        self.ontfs.remember("a", "custom:one", "two", obj_is_literal=True)
        self.assertEqual(len(self.ontfs.contradictions()), 1)

    def test_atomic_write_preserves_original_when_replace_fails(self):
        target = Path(self.test_dir.name) / "atomic.txt"
        target.write_text("original", encoding="utf-8")
        with patch("ontfs.storage.os.replace", side_effect=OSError("simulated crash")):
            with self.assertRaises(OSError):
                atomic_write(target, "replacement")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_concurrent_process_links_are_not_lost(self):
        count = 5
        script = (
            "from ontfs.core import OntFS; import sys; "
            "OntFS(sys.argv[1]).link('a', 'custom:r', sys.argv[2])"
        )
        repo_root = Path(__file__).resolve().parents[1]
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script, self.test_dir.name, f"b{i}"],
                cwd=repo_root,
            )
            for i in range(count)
        ]
        self.assertEqual([process.wait(timeout=15) for process in processes], [0] * count)
        reloaded = OntFS(self.test_dir.name)
        predicate = reloaded.graph.resolve_uri("custom:r")
        self.assertEqual(len(list(reloaded.graph.graph.objects(None, predicate))), count)

    def test_graph_file_uris_are_relocatable_and_migratable(self):
        from rdflib import URIRef
        old_path = f"file://{Path(self.test_dir.name).resolve()}/old.py"
        predicate = self.ontfs.graph.resolve_uri("custom:uses")
        self.ontfs.graph.graph.add((URIRef(old_path), predicate, URIRef("https://example.org")))
        self.ontfs.graph.is_dirty = True
        self.ontfs.graph.save()
        result = self.ontfs.migrate_uris()
        self.assertGreater(result["triples_changed"], 0)
        migrated = OntFS(self.test_dir.name)
        self.assertEqual(
            str(migrated.graph.resolve_uri(old_path)),
            str(migrated.graph.resolve_uri("./old.py")),
        )
        self.assertEqual(
            len(list(migrated.graph.graph.subjects(predicate, URIRef("https://example.org")))), 1
        )

    def test_context_and_graph_boost_survive_directory_move(self):
        from rdflib import URIRef
        Path(self.test_dir.name, "design.md").write_text(
            "Unique needleword architecture details.\n", encoding="utf-8"
        )
        self.ontfs.link("./design.md", "custom:documents", "custom:service")
        original_context = self.ontfs.context("custom:service")
        original_search = self.ontfs.search("needleword", related_to="custom:service")
        moved = Path(self.test_dir.name, "relocated")
        shutil.copytree(self.test_dir.name, moved, ignore=shutil.ignore_patterns("relocated"))
        copied = OntFS(str(moved))
        moved_context = copied.context("custom:service")
        moved_search = copied.search("needleword", related_to="custom:service")
        self.assertEqual(
            original_context["facts"][0]["predicate"],
            moved_context["facts"][0]["predicate"],
        )
        self.assertEqual(original_search["results"][0]["uri"], moved_search["results"][0]["uri"])
        self.assertNotEqual(original_search["results"][0]["path"], moved_search["results"][0]["path"])

    def test_entity_status_and_superseded_context_filter(self):
        self.ontfs.link("./replacement.py", "custom:references", "./legacy.py")
        self.ontfs.supersede("./replacement.py", "./legacy.py", note="Replaced module")
        self.assertEqual(self.ontfs.graph.entity_status("./legacy.py"), "superseded")
        self.assertEqual(self.ontfs.context("./replacement.py")["facts"], [])
        visible = self.ontfs.context("./replacement.py", include_superseded=True)
        self.assertEqual(len(visible["facts"]), 1)
        self.ontfs.set_entity_status("./replacement.py", "verified")
        self.assertEqual(self.ontfs.context("./replacement.py")["entity_status"], "verified")

    def test_boolean_tag_selection_precedence_hierarchy_and_negation(self):
        for name in ("Alpha", "Beta", "Experimental", "Project"):
            self.ontfs.remember(
                f"custom:tag:{name}", "skos:prefLabel", name,
                obj_is_literal=True,
            )
        self.ontfs.link("custom:tag:Alpha", "skos:broader", "custom:tag:Project")
        self.ontfs.link("custom:tag:Beta", "skos:broader", "custom:tag:Project")
        self.ontfs.link("./one.py", "ontfs:hasTag", "custom:tag:Alpha")
        self.ontfs.link("./two.py", "ontfs:hasTag", "custom:tag:Beta")
        self.ontfs.link("./excluded.py", "ontfs:hasTag", "custom:tag:Experimental")
        selected = self.ontfs.select("Project & !Experimental")
        self.assertEqual(
            {entry["path"] for entry in selected["resources"]},
            {str(Path(self.test_dir.name, "one.py")), str(Path(self.test_dir.name, "two.py"))},
        )
        self.assertEqual(len(self.ontfs.select("Alpha | Beta")["resources"]), 2)
        with self.assertRaisesRegex(ValueError, "unknown tag"):
            self.ontfs.select("Unknown")

    def test_boolean_selector_rejects_malformed_expression(self):
        with self.assertRaises(ValueError):
            self.ontfs.select("Alpha & (Beta")

    def test_recall_is_budgeted_pointer_only_and_filters_superseded(self):
        self.ontfs.remember("custom:concept:db", "skos:prefLabel", "database", obj_is_literal=True)
        self.ontfs.remember("custom:concept:db", "skos:altLabel", "data store", obj_is_literal=True)
        self.ontfs.link("./current.md", "custom:about", "custom:concept:db")
        self.ontfs.remember("./current.md", "dcterms:abstract", "A safe short summary", obj_is_literal=True)
        self.ontfs.remember("./current.md", "custom:payload", "PRIVATE_FILE_CONTENT", obj_is_literal=True)
        self.ontfs.link("./old.md", "custom:about", "custom:concept:db")
        self.ontfs.set_entity_status("./old.md", "superseded")
        result = self.ontfs.recall("data store", search_text=False, limit=1)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["path"], str(Path(self.test_dir.name, "current.md")))
        self.assertEqual(result["results"][0]["summary"], "A safe short summary")
        self.assertNotIn("PRIVATE_FILE_CONTENT", json.dumps(result))
        self.assertGreater(result["stats"]["approx_tokens"], 0)

    def test_recall_rejects_invalid_budget(self):
        with self.assertRaises(ValueError):
            self.ontfs.recall("query", max_tokens=0)

    def test_shacl_max_count_marks_a_predicate_functional_for_conflicts(self):
        shapes = Path(self.test_dir.name, ".ontfs.shapes.ttl")
        shapes.write_text(
            """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://ontfs.example.org/custom#> .
ex:Shape a sh:NodeShape ; sh:property [ sh:path ex:limited ; sh:maxCount 1 ] .
""", encoding="utf-8"
        )
        self.ontfs.remember("a", "custom:limited", "one", obj_is_literal=True)
        self.ontfs.remember("a", "custom:limited", "two", obj_is_literal=True)
        self.assertEqual(len(self.ontfs.contradictions()), 1)

    @unittest.skipUnless(importlib.util.find_spec("pyshacl"), "optional pyshacl dependency is unavailable")
    def test_shacl_validation_and_proposal_cardinality(self):
        shapes = Path(self.test_dir.name, ".ontfs.shapes.ttl")
        shapes.write_text(
            """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://ontfs.example.org/custom#> .
ex:Shape a sh:NodeShape ; sh:targetSubjectsOf ex:state ;
  sh:property [ sh:path ex:state ; sh:maxCount 1 ; sh:in ( "active" "verified" ) ] .
""", encoding="utf-8"
        )
        self.ontfs.remember("a", "custom:state", "active", obj_is_literal=True)
        self.assertTrue(self.ontfs.validate()["conforms"])
        proposal = self.ontfs.propose_link("a", "custom:state", "invalid", obj_is_literal=True)
        self.assertFalse(self.ontfs.validate_proposal(proposal["id"])["valid"])

    @unittest.skipUnless(importlib.util.find_spec("pyshacl"), "optional pyshacl dependency is unavailable")
    def test_shacl_proposal_ignores_unrelated_preexisting_violation(self):
        shapes = Path(self.test_dir.name, ".ontfs.shapes.ttl")
        shapes.write_text(
            """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://ontfs.example.org/custom#> .
ex:Shape a sh:NodeShape ; sh:targetSubjectsOf ex:state ;
  sh:property [ sh:path ex:state ; sh:in ( "active" "verified" ) ] .
""", encoding="utf-8"
        )
        self.ontfs.remember("a.md", "custom:state", "invalid", obj_is_literal=True)
        proposal = self.ontfs.propose_link("b.md", "custom:state", "active", obj_is_literal=True)

        self.assertFalse(self.ontfs.validate()["conforms"])
        self.assertTrue(self.ontfs.validate_proposal(proposal["id"])["valid"])

    @unittest.skipUnless(importlib.util.find_spec("pyshacl"), "optional pyshacl dependency is unavailable")
    def test_shacl_proposal_rejects_worsened_max_count_violation(self):
        shapes = Path(self.test_dir.name, ".ontfs.shapes.ttl")
        shapes.write_text(
            """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://ontfs.example.org/custom#> .
ex:Shape a sh:NodeShape ; sh:targetSubjectsOf ex:state ;
  sh:property [ sh:path ex:state ; sh:maxCount 1 ] .
""", encoding="utf-8"
        )
        self.ontfs.remember("a.md", "custom:state", "one", obj_is_literal=True)
        self.ontfs.remember("a.md", "custom:state", "two", obj_is_literal=True)
        proposal = self.ontfs.propose_link("a.md", "custom:state", "three", obj_is_literal=True)

        self.assertFalse(self.ontfs.validate_proposal(proposal["id"])["valid"])

    def test_multiple_evidence_records_and_status_history(self):
        first = self.ontfs.remember(
            "./claim", "custom:sourceFact", "value", obj_is_literal=True,
            source="./one.md", confidence=0.6,
        )
        second = self.ontfs.remember(
            "./claim", "custom:sourceFact", "value", obj_is_literal=True,
            source="./two.md", confidence=0.9,
        )
        self.assertEqual(first, second)
        record = self.ontfs.fact(first)
        self.assertEqual(record["evidenceCount"], 2)
        self.assertAlmostEqual(record["confidence"], 0.9)
        self.ontfs.set_fact_status(first, "verified", "reviewed")
        self.ontfs.set_fact_status(first, "stale", "outdated")
        history = self.ontfs.fact(first)["statusHistory"]
        self.assertEqual([event["to"] for event in history], ["verified", "stale"])

    def test_hybrid_search_boosts_graph_related_documents(self):
        Path(self.test_dir.name, "design.md").write_text(
            "Database migration plan and rollback steps.\n", encoding="utf-8"
        )
        Path(self.test_dir.name, "notes.md").write_text(
            "Database migration plan and database migration notes.\n", encoding="utf-8"
        )
        self.ontfs.link("./design.md", "custom:documents", "./service.py")
        results = self.ontfs.search(
            "database migration", related_to="./service.py", limit=2
        )["results"]
        self.assertEqual(results[0]["path"], str(Path(self.test_dir.name, "design.md")))
        self.assertEqual(results[0]["graph_boost"], 5)
        self.assertIn("rollback", results[0]["snippet"])

    def test_search_validates_query_and_limit(self):
        with self.assertRaises(ValueError):
            self.ontfs.search("", limit=1)
        with self.assertRaises(ValueError):
            self.ontfs.search("anything", limit=0)

    def test_vector_search_returns_embedding_scores(self):
        Path(self.test_dir.name, "storage.md").write_text(
            "Database storage uses durable records.\n", encoding="utf-8"
        )
        Path(self.test_dir.name, "unrelated.md").write_text(
            "Authentication tokens expire quickly.\n", encoding="utf-8"
        )
        result = self.ontfs.search(
            "database storage", vector=True, embedding_dimensions=64
        )
        self.assertTrue(result["vector"])
        self.assertEqual(result["embedding_dimensions"], 64)
        self.assertEqual(result["results"][0]["path"], str(Path(self.test_dir.name, "storage.md")))
        self.assertGreater(result["results"][0]["vector_score"], 0)
        self.assertEqual(result["embedding_backend"], "hashed")

        with self.assertRaises(ValueError):
            self.ontfs.search("database", vector=True, embedding_dimensions=0)

    def test_embedding_cache_reuses_and_invalidates_content(self):
        from ontfs.embeddings import HashedBackend, cached_embedding

        backend = HashedBackend(32)
        path = Path(self.test_dir.name, "cached.md")
        path.write_text("first contents", encoding="utf-8")
        with patch.object(backend, "embed", wraps=backend.embed) as embedder:
            first = cached_embedding(self.ontfs, backend, path.read_text(), path)
            cached_embedding(self.ontfs, backend, path.read_text(), path)
            self.assertEqual(embedder.call_count, 1)
            path.write_text("changed contents", encoding="utf-8")
            second = cached_embedding(self.ontfs, backend, path.read_text(), path)
            self.assertEqual(embedder.call_count, 2)
        self.assertNotEqual(first, second)

    def test_hashed_backend_preserves_existing_embedding_output(self):
        from ontfs.embeddings import HashedBackend, embed
        self.assertEqual(HashedBackend(64).embed(["same text"])[0], embed("same text", 64))

    @unittest.skipIf(create_server is None, "optional MCP dependency is unavailable")
    def test_mcp_server_exposes_agent_tools(self):
        server = create_server(self.test_dir.name)
        tools = set(server._tool_manager._tools)
        self.assertEqual(tools, {
            "context", "search", "scan", "select", "recall", "set_entity_status", "supersede", "propose_link",
            "validate_proposal", "commit_proposal", "set_fact_status",
            "contradictions", "validate",
        })
        self.assertEqual(server._tool_manager._tools["context"].fn(
            "./missing.py", depth=1, limit=5
        )["facts"], [])


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
