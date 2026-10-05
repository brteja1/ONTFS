"""Microbenchmark indexed neighborhood traversal against a full scan.

Run with ``python tests/bench_context.py``. This is diagnostic, not a unit test.
"""

import time

from rdflib import Graph, URIRef


def main():
    graph = Graph()
    nodes = [URIRef(f"urn:bench:{index}") for index in range(100_001)]
    predicate = URIRef("urn:bench:edge")
    for index in range(100_000):
        graph.add((nodes[index], predicate, nodes[index + 1]))
    root = nodes[50_000]

    start = time.perf_counter()
    baseline = [triple for triple in graph if root in (triple[0], triple[2])]
    baseline_seconds = time.perf_counter() - start

    start = time.perf_counter()
    indexed = set(graph.triples((root, None, None)))
    indexed.update(graph.triples((None, None, root)))
    indexed_seconds = time.perf_counter() - start
    assert set(baseline) == indexed
    print(f"triples={len(graph)} neighborhood={len(indexed)}")
    print(f"full_scan_seconds={baseline_seconds:.6f}")
    print(f"indexed_seconds={indexed_seconds:.6f}")
    print(f"speedup={baseline_seconds / max(indexed_seconds, 1e-12):.1f}x")


if __name__ == "__main__":
    main()
