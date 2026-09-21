# OntFS: Ontology Knowledge Graph CLI
## Technical Design Document

**System**: OntFS - A CLI tool for creating and managing an RDF-based knowledge graph mapping URLs and local files.

---

### 1. Overview
OntFS manages an ontology-based knowledge graph. Unlike traditional tagging systems (which are bipartite and strict), OntFS allows any URI (filesystem path, web URL, or abstract concept) to be linked to any other URI via customizable relations. The tool stores this knowledge graph natively as an RDF Turtle file (`.ontfs.ttl`) in the working directory.

### 2. Data Model & Ontology
OntFS leverages standard semantic web vocabularies, primarily **SKOS** (Simple Knowledge Organization System), **OWL** (Web Ontology Language), and **RDFS** (RDF Schema).

*   **Entities**: Represented as URIs. Local files use the `file://` scheme, web pages use `http:// or https://`, and custom abstract concepts use a custom namespace (e.g., `ontfs:Concept`).
*   **Relations (Properties)**: Are themselves URIs in the graph. 
    *   **Standard Relations**: `skos:broader`, `skos:narrower`, `skos:related`.
    *   **Custom Relations**: Users can define new properties (e.g., `custom:dependsOn`).
*   **Property Characteristics**: Relations can be adorned with OWL axioms to support advanced querying (e.g., `owl:TransitiveProperty`, `owl:SymmetricProperty`, `rdfs:subPropertyOf`).

### 3. Architecture
The system consists of the following layers:

1.  **CLI Layer (`cli.py`)**: Provides an ergonomic command-line interface. It uses a "hybrid" approach to relations—offering simple flags for common OWL axioms (like `--transitive`) while falling back to universal triples for advanced cases.
2.  **Core API (`core.py`)**: The primary Python interface (`OntFS` class). Handles path normalization, namespace resolution, and delegates work to the RDF handler.
3.  **RDF Handler (`rdf_handler.py`)**: Wraps the `rdflib` library. It manages loading/saving the `.ontfs.ttl` file, graph updates, and SPARQL query execution.
4.  **Namespace Manager (`namespaces.py`)**: Manages the binding of prefixes (like `skos:`, `owl:`, `rdf:`, and `custom:`) so users can type concise commands instead of full URIs.

### 4. CLI Interface Design
The CLI is designed to be intuitive, borrowing ergonomic concepts from HTFS but applying them to a general graph model.

*   `ontfs init`: Initializes an empty `.ontfs.ttl` file with standard namespace bindings.
*   `ontfs add-relation <predicate_uri> [--type object|datatype] [--transitive] [--symmetric] [--inverse <uri>] [--subprop-of <uri>]`: Syntactic sugar to define a new property with OWL axioms.
*   `ontfs link <subject> <predicate> <object>`: Adds a single RDF triple to the graph.
*   `ontfs unlink <subject> <predicate> <object>`: Removes a triple.
*   `ontfs query <expr>`: Executes a SPARQL query (or a simplified AST-based query language) against the graph to resolve entities.

### 5. Emulating TagFS with OntFS
Because OntFS is a generalized knowledge graph, it can emulate the behavior of HTFS (a hierarchical tagging system) perfectly.
*   **Tags** become `skos:Concept` entities.
*   **Tag Hierarchy** is expressed using `skos:broader`.
*   **Resource Tagging** is expressed using a custom relation, e.g., `ontfs:hasTag` linking a `file://` URL to a `skos:Concept`.
*   A query for a tag includes evaluating the transitive closure of `skos:broader`, which OntFS natively supports via SPARQL property paths.

An `examples/tagfs_emulation/` directory will be provided to demonstrate this exact mapping.
