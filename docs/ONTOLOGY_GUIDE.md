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

## 7. Safe agent mutations

Agents can stage a proposed link without modifying `.ontfs.ttl`:

```bash
ontfs propose-link ./service.py custom:dependsOn ./database.py \
  --source ./architecture.md --confidence 0.9
```

Review and apply it explicitly:

```bash
ontfs proposals --status proposed
ontfs validate-proposal <proposal-id>
ontfs commit-proposal <proposal-id>
```

Or reject it with an audit reason:

```bash
ontfs reject-proposal <proposal-id> --reason "Evidence is insufficient"
```

Proposal records and their status history are stored in
`.ontfs.proposals.json`; committed facts remain in the RDF graph.

## 8. Repository scanning

The scanner creates useful initial context for coding agents without requiring
manual links:

```bash
ontfs scan .
```

Currently it indexes Python files, top-level imports, and Git commit/branch
metadata. Scan results use ordinary RDF relationships, so they are available
through both `context` and SPARQL. Use `--no-git` when Git provenance is not
needed.

To keep a development graph current, use the dependency-free polling watcher:

```bash
ontfs watch . --interval 2
```

Use `--iterations N` for a bounded run. The watcher rescans the selected path
when a Python file is added, changed, or removed.

## 9. Fact lifecycle

Facts can expire or require review. Supported statuses are `asserted`,
`verified`, `stale`, `disputed`, and `retracted`:

```bash
ontfs link ./service.py custom:owner team-a --literal \
  --expires-at 2026-12-31T00:00:00+00:00
ontfs refresh-facts
ontfs fact <fact-id>
ontfs fact-status <fact-id> verified
ontfs contradictions --mark
```

Contradiction detection groups active facts by subject and predicate and
reports different object values. Marking a conflict changes the involved facts
to `disputed`. Retraction keeps the reified fact and its metadata for audit,
but removes the direct assertion from agent context.

Only predicates declared with `owl:FunctionalProperty` are considered for
contradictions. Declare a single-valued relation with:

```bash
ontfs add-relation custom:owner --functional
```

Older graphs can be converted to relocatable local file identifiers with
`ontfs migrate-uris --dry-run` followed by `ontfs migrate-uris`. Back up the
Turtle graph first; fact IDs that include local file terms are remapped, and
proposal references are updated.

## 10. Hybrid search

Use `search` when an agent needs both textual relevance and graph context:

```bash
ontfs search "database migration" --related-to ./service.py --limit 10
```

Results include a score, text-hit count, graph boost, and a short snippet. The
current implementation uses bounded local lexical search. Vector ranking can
also be enabled without an external model:

```bash
ontfs search "durable data storage" --vector --embedding-dimensions 256
```

Vector mode uses deterministic hashed embeddings and combines cosine, lexical,
and graph scores. The persistent cache lives in `.ontfs.vectors/`; the watcher
evicts vectors for changed or removed files. `--hashed` is the descriptive
option name, while `--vector` remains a compatibility alias. Install
`.[embed]` to select a local Sentence Transformers model with
`--embedding-backend sentence-transformers` and optionally
`--embedding-model <name>`.

## 11. MCP integration

MCP support is optional:

```bash
pip install -e '.[mcp]'
ontfs-mcp --directory .
```

The MCP server exposes `context`, `search`, `recall`, `select`, `scan`, graph
validation, proposal workflow, lifecycle, and contradiction tools. Each server instance is scoped to the
directory passed through `--directory`; the core ONTFS package remains usable
without installing MCP.

See the dedicated [MCP Guide](MCP_GUIDE.md) for the complete tool contract,
transport options, and safe mutation workflow.

## 12. Entity lifecycle

Entity lifecycle is separate from fact lifecycle. An entity can be marked
`active`, `verified`, `experimental`, `stale`, `superseded`, or `deprecated`:

```bash
ontfs entity-status ./new-design.md verified --reason "Reviewed"
ontfs supersede ./new-design.md ./old-design.md --note "Replaces the old design"
ontfs context ./new-design.md
ontfs context ./new-design.md --include-superseded
```

Context reports the root entity status and hides superseded neighbors by
default. Set `--include-superseded` to include their ordinary neighboring facts;
the lifecycle bookkeeping predicates themselves remain omitted from context.

## 13. Boolean tag selection

Select resources using `&`, `|`, `!`, and parentheses. Precedence is `!`, then
`&`, then `|`:

```bash
ontfs select '(Research | Project) & !Archived' --limit 50
```

Tags can be resolved by prefixed URI, `skos:prefLabel`, `skos:altLabel`, or
`skos:hiddenLabel`. Hierarchical child tags match their broader parent.

## 14. Budgeted pointer recall

`recall` resolves query terms against preferred, alternate, hidden, and RDFS
labels, then returns linked resources as pointers. It filters retracted facts
and superseded entities by default and never includes file bodies. Summaries
are read only from the configured summary predicate (default
`dcterms:abstract`):

```bash
ontfs recall "data store" --limit 6 --max-tokens 1200
ontfs recall "data store" --no-text-search
```

The response includes `why` explanations and approximate token/cap statistics.
Local text search may contribute ranked pointers, but snippets are not copied
into recall output.

## 15. Context traversal benchmark

Run `python tests/bench_context.py` to compare indexed adjacency lookup with a
full graph scan on a synthetic 100,000-triple graph. On the current developer
environment, the root neighborhood took about 0.00008s indexed versus 0.19s
for a full scan (roughly 2,400x for this microbenchmark). This isolates
traversal; it does not measure Turtle parsing, so it does not justify adopting
an additional persistent store backend by itself.
