# OntFS: Ontology Knowledge Graph CLI

OntFS is a command-line tool that bridges the gap between the rigid, bipartite world of file tagging and the powerful, but complex, world of Semantic Web ontologies (RDF, SKOS, OWL). 

It allows you to organize local files, web URLs, and abstract concepts into a massive, queryable knowledge graph stored directly in your filesystem.

## 🎯 Project Purpose
Traditional tagging systems (like HTFS) only let you link "Files" to "Tags." 
OntFS breaks this limitation. It provides a generalized knowledge graph where any URI (whether a local `./script.py`, a remote `https://github.com`, or an abstract `custom:Concept`) can be linked to any other URI using **customizable relations**.

The goal is to provide the extreme expressive power of an ontology editor (like Protégé) wrapped in an ergonomic, Git-like CLI.

Furthermore, because it uses standard RDF and provides a simple programmatic CLI interface, **OntFS is highly valuable for LLM agents**, enabling them to autonomously build and navigate persistent local knowledge bases.

## 🔭 Scope
*   **Entities**: First-class support for Local Files (automatically resolved to absolute `file:///` URIs), Web URLs, and prefixed Ontology Concepts.
*   **Relations**: Users can define custom relationships (e.g., `dependsOn`, `authoredBy`, `isPeerOf`).
*   **Ontology Characteristics**: Easy CLI flags to apply powerful OWL axioms to your relations (e.g., making a relation Transitive, Symmetric, or the Inverse of another).
*   **Storage**: Pure RDF backend. All knowledge is serialized to a portable `.ontfs.ttl` Turtle file in the working directory using `rdflib`.
*   **Querying**: Native support for SPARQL queries, allowing for complex graph traversals (like transitive closures) out of the box.

## 📐 Design Overview
OntFS relies on standard Semantic Web vocabularies:
*   **SKOS** (Simple Knowledge Organization System) for hierarchical concepts.
*   **OWL** (Web Ontology Language) for defining the logical properties of relations.
*   **RDF** (Resource Description Framework) as the underlying triple-store.

The architecture is split into a **Core API** (`ontfs.core`) that handles the graph logic and URI resolution, and an **Argparse CLI** (`ontfs.cli`) that exposes a "hybrid" approach to the user. The CLI provides simple flags for 90% of ontology modeling needs, while still supporting raw triples for advanced use cases.

Because OntFS is a generalized graph, it can effortlessly emulate stricter systems. See the `examples/tagfs_emulation` folder for a demonstration of how OntFS perfectly replicates a hierarchical tag file system.

## 📚 Documentation
For detailed guides on how to use the CLI and model data, please see the internal documentation:
*   [Ontology Guide](docs/ONTOLOGY_GUIDE.md): Learn how to define relations and link entities.
*   [Technical Design](DESIGN.md): Deep dive into the architecture and internal data model.
*   [TagFS Emulation](examples/tagfs_emulation/README.md): See how to build a tagging system on top of OntFS.

## 🚀 Quick Start
```bash
# Install the CLI
pip install -e .

# Initialize the graph in the current directory
ontfs init


# Define a transitive relationship
ontfs add-relation custom:dependsOn --transitive

# Or batch define relations and links using JSON
ontfs add-relations relations.json
ontfs batch-link links.json


# Link files
ontfs link ./backend.py custom:dependsOn ./database.py
```

## 🧪 Testing
Run the test suite using the provided bash script:
```bash
./tests/run_tests.sh
```

## 🤖 Agent Context and Evidence

ONTFS can retain explainability metadata alongside an asserted relationship.
The original RDF triple remains available to normal SPARQL clients, while the
statement is also recorded with a stable fact ID, observation time, and any
optional evidence supplied by the caller.

```bash
ontfs link ./service.py custom:dependsOn ./database.py \
  --source ./architecture.md \
  --confidence 0.9 \
  --asserted-by build-agent \
  --note "Found in architecture document"
```

Agents can retrieve bounded JSON context without constructing a SPARQL query:

```bash
ontfs context ./service.py --depth 2 --limit 30
```

The response includes neighboring RDF facts and their evidence, confidence,
fact ID, and observation time. This is intended as the first layer of an
agent-native memory workflow; repository scanning, fact validation, and
proposal/commit workflows are described in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Agents can stage a mutation for review before it changes the graph:

```bash
proposal=$(ontfs propose-link ./service.py custom:dependsOn ./database.py \
  --source ./architecture.md --confidence 0.9)
ontfs proposals --status proposed
ontfs validate-proposal <proposal-id>
ontfs commit-proposal <proposal-id>
```

Use `ontfs reject-proposal <proposal-id> --reason "..."` to reject it. Proposal
status transitions and commit/rejection events are stored in
`.ontfs.proposals.json`.

ONTFS can also build an initial codebase graph from Python files:

```bash
ontfs scan .
```

The scanner records source files, imported top-level modules, and the current
Git commit and branch when the path is inside a Git repository. Use
`ontfs scan . --no-git` to omit Git metadata.

For a development checkout, ONTFS can poll for Python file changes and rescan
automatically:

```bash
ontfs watch . --interval 2
```

Use `--iterations N` for a bounded run in automation or tests. The watcher is
polling-based and currently rescans the selected path when any Python file
changes.
