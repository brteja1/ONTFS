# OntFS Ontology Guide

OntFS is a generic Ontology File System CLI based on Semantic Web standards (RDF, SKOS, OWL). This guide explains how to model data using the OntFS CLI.

## 1. What are Entities?
An entity in OntFS is a **URI**. Because we deal with files and the web, URIs are incredibly powerful.
- **Local Files**: `./document.pdf` is automatically resolved to a URI like `file:///path/to/document.pdf`.
- **Web URLs**: `https://github.com/`
- **Abstract Concepts**: Prefixed URIs like `skos:Concept` or `custom:Project`.

## 2. What are Relations?
Relations (Predicates) connect two entities.
OntFS allows you to define your own custom relations and apply OWL (Web Ontology Language) characteristics to them.

### Defining a Relation
```bash
ontfs add-relation custom:dependsOn --type object --transitive
```

### Applying a Relation (Linking)
```bash
ontfs link ./backend.py custom:dependsOn ./database.py
ontfs link ./database.py custom:dependsOn ./os.py
```

## 3. OWL Characteristics Exposed via CLI

### `--transitive`
If A relates to B, and B relates to C, then A implicitly relates to C.
**Example**: `skos:broader` (hierarchies). If `Dog` is broader than `Mammal`, and `Mammal` is broader than `Animal`, a query for `Animal` can automatically find `Dog`.
```bash
ontfs add-relation custom:isChildOf --transitive
```

### `--symmetric`
If A relates to B, then B implicitly relates to A.
**Example**: `skos:related`.
```bash
ontfs add-relation custom:isPeerOf --symmetric
ontfs link fileA custom:isPeerOf fileB
# Automatically means fileB is peer of fileA
```

### `--inverse`
Links two different relations as opposites.
```bash
ontfs add-relation custom:blocks --inverse custom:isBlockedBy
ontfs link bugA custom:blocks bugB
# Automatically means bugB custom:isBlockedBy bugA
```

### `--subprop-of`
Defines a hierarchy of relations.
```bash
ontfs add-relation custom:stronglyDependsOn --subprop-of custom:dependsOn
```
If you query for `custom:dependsOn`, it will also match any triples linked via `custom:stronglyDependsOn`.

## 4. Querying
You can query the graph using standard SPARQL syntax.
```bash
ontfs query "SELECT ?s WHERE { ?s custom:dependsOn <file:///path/to/database.py> }"
```

### Batch Operations
To improve performance when manipulating a large number of relations or links, use the batch commands which accept a JSON file:

- **Add Multiple Relations**: `ontfs add-relations relations.json`
- **Add Multiple Links**: `ontfs batch-link links.json`
- **Remove Multiple Links**: `ontfs batch-unlink unlinks.json`

The file format is an array of objects corresponding to the arguments of the individual commands.

## 5. Evidence-backed facts for agents

Every linked RDF statement receives a stable fact identifier and observation
timestamp. Agents can attach evidence and attribution when creating a link:

```bash
ontfs link ./service.py custom:dependsOn ./database.py \
  --source ./architecture.md \
  --confidence 0.9 \
  --asserted-by build-agent \
  --note "Found in architecture document"
```

`--confidence` must be between `0` and `1`. The original direct RDF triple is
preserved for normal SPARQL consumers; metadata is represented using standard
RDF statement reification and can be returned to an agent as evidence.

## 6. Agent context retrieval

The `context` command provides bounded JSON around an entity without requiring
an agent to construct SPARQL:

```bash
ontfs context ./service.py --depth 2 --limit 30
```

Each returned fact includes its subject, predicate, object, fact ID, source,
confidence, asserting agent, note, and observation time when available. The
depth and limit bounds are intended to keep retrieved context predictable and
within an agent's token budget.
