import os
import tempfile
import unittest
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

if __name__ == "__main__":
    unittest.main()
