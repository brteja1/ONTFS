# Implementation Plan for OntFS

This document outlines the step-by-step plan for bootstrapping and developing the OntFS CLI tool.

## Phase 1: Project Setup and Skeleton
1. **Initialize Project**: Create `pyproject.toml` with `setuptools` build configuration and `rdflib` as the primary dependency.
2. **Directory Structure**: Create the `ontfs/` package directory along with `__init__.py` and `__main__.py` to allow execution via `python -m ontfs`.
3. **Core Files**: Create empty or boilerplate files for `cli.py`, `core.py`, `rdf_handler.py`, and `namespaces.py`.

## Phase 2: Core Data and RDF Layer
1. **`namespaces.py`**: Define constants for RDF, RDFS, OWL, SKOS, and a default custom namespace (e.g., `local:` or `ontfs:`). Provide a utility to bind these to an `rdflib.Graph`.
2. **`rdf_handler.py`**: 
    * Implement `OntFSGraph` class wrapping `rdflib.Graph`.
    * Implement `.ontfs.ttl` loading and saving logic.
    * Implement primitive triple operations: `add_triple(s, p, o)` and `remove_triple(s, p, o)`.
    * Implement URI resolution (converting `file:///` paths, web URLs, and prefixed URIs like `skos:Concept` into proper `rdflib.URIRef` objects).

## Phase 3: High-Level Core Logic
1. **`core.py`**: 
    * Implement `init_graph()` to bootstrap the file.
    * Implement `define_relation(uri, type, is_transitive, is_symmetric, inverse_of, subprop_of)` using the RDF handler to emit the correct OWL triples.
    * Implement `link(subject, predicate, object)`.
    * Implement `unlink(...)`.

## Phase 4: CLI Interface
1. **`cli.py`**: Set up `argparse` with subcommands:
    * `init`
    * `add-relation` (with all the hybrid approach flags)
    * `link`
    * `unlink`
    * `query` (a basic implementation to start, perhaps accepting raw SPARQL or a specific entity to lookup).
2. Wire the CLI commands directly to `core.py` methods.

## Phase 5: Documentation
1. **`docs/ONTOLOGY_GUIDE.md`**: Create an elaborate guide explaining:
    * The basics of SKOS and OWL as it applies to OntFS.
    * How to model custom relations (e.g., dependencies, authorship, groupings).
    * Detailed examples of the CLI options (transitive, symmetric, etc.) and what they mean practically for file organization.

## Phase 6: TagFS Emulation Example
1. **`examples/tagfs_emulation/`**:
    * Create a `README.md` that maps `tagfs` commands directly to `ontfs` commands.
    * Provide a wrapper shell script (`tagfs_wrapper.sh`) that intercepts commands like `tagfs addtags A/B/C` and translates them into `ontfs link B skos:broader A` and `ontfs link C skos:broader B`.
    * Provide an example of how to query for files using a tag and all its descendants via SPARQL property paths (`skos:broader*`).
