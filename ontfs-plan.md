# Implementation Plan: ONTFS Proposals P1–P10

This plan covers the **ONTFS-side** work: implementing the proposals in
[FUTURE.md](FUTURE.md) ("Proposals from localkb integration research"). The
work is general-purpose; the `localkb` plugin motivated it but nothing here
depends on localkb.

The localkb migration that consumes these features is planned separately in
`/local-ssd/rboggava/Xperiments/skill_development/localkb/PLAN.md`.

Guiding principles:

- **Correctness and safety before features.** Fix the behaviours that would
  corrupt or mislabel data (P1, P3, P4) before adding capabilities.
- **Backwards compatible by default.** Existing `.ontfs.ttl` graphs must keep
  loading; any format change ships with a migration command.
- **Optional extras stay optional.** New heavy dependencies (pyshacl, neural
  embeddings, pyoxigraph) go behind `pyproject.toml` extras, like `mcp`.
- **Agents get pointers, not payloads.** New retrieval surfaces are capped and
  return URIs plus reasons (P10).
- **Every phase is test-gated.** Each task adds `unittest` cases to `tests/`
  and must pass `./tests/run_tests.sh`.

---

## Phase 1 — Correctness and safety foundations

Goal: ONTFS can safely back a multi-session agent knowledge base.

### 1.1 Functional-property contradiction gating (P1)

**Status: complete.**

- `rdf_handler.py`
  - `define_relation()`: accept `functional=True` and add
    `owl:FunctionalProperty` to the predicate.
  - `contradictions()`: skip any predicate that is not typed
    `owl:FunctionalProperty`. Keep the existing grouping logic otherwise.
- `cli.py`: add `--functional` to `add-relation`; accept `"functional": true`
  in `add-relations` JSON.
- `core.py` / `mcp_server.py`: pass the flag through; the MCP
  `contradictions` tool is unchanged in signature.
- Tests:
  - multi-valued predicate with two objects → no conflict.
  - functional predicate with two objects → one conflict; `--mark` sets both
    facts `disputed`.
  - retracted facts are still ignored.
- Docs: README "Facts also have a lifecycle" section and ONTOLOGY_GUIDE.
- **Behaviour change note:** graphs that relied on the old (over-reporting)
  behaviour will see fewer conflicts. Call out in the changelog.

### 1.2 Concurrency-safe persistence (P4)

**Status: implementation complete; Linux concurrency and atomic replacement
tests pass.**

- New helper module `ontfs/storage.py`:
  - `locked(path)`: context manager using `fcntl.flock` on
    `<graph>.lock` (Windows fallback: `msvcrt.locking` or a lock-file with
    O_EXCL; document if unsupported).
  - `atomic_write(path, data)`: write to `path.tmp` in the same directory,
    `fsync`, `os.replace()`.
- `RDFHandler`:
  - `save()` uses `atomic_write`.
  - Add `transaction()` context manager: acquire lock → reload graph from disk
    → yield → save → release. Mutating `OntFS` methods (`link`, `remember`,
    `unlink`, `batch_*`, `set_fact_status`, `refresh_stale`,
    `contradictions(mark=True)`, `commit_proposal`, `scan`) run inside it.
- `OntFS._save_proposals()` / `_load_proposals()`: same lock + atomic write.
- Tests:
  - spawn N subprocesses each running `ontfs link a custom:r bN`; assert all N
    triples present.
  - simulated crash (exception between write and replace) leaves the original
    file intact.

### 1.3 Stable, relocatable identifiers (P3)

**Status: implementation complete; migration command and path resolution are
covered by tests. A manual TagFS emulation run against the new identifiers
returns its resource path correctly.**

**Phase 1 status: complete.**

- Decide the URI scheme (recommendation: `ontfs:file/<posix-relative-path>`
  under the graph's own namespace, which keeps Turtle readable and avoids
  `@base` serialization quirks in rdflib).
- `resolve_uri()`:
  - local paths inside the graph directory → relative file URI.
  - paths outside the directory → keep absolute `file:///` (documented).
  - existing `file:///` URIs inside the directory are accepted and normalized.
- Add `RDFHandler.to_path(uri)` and use it wherever output shows paths
  (`context`, `search`, `scan`, MCP tools) so callers still receive absolute
  paths.
- `scanner.py`, `search.py`: compare entities via the normalized form (search
  currently matches `file.resolve().as_uri()` against related URIs).
- New command `ontfs migrate-uris [--dry-run]`: rewrites absolute file URIs
  under the directory into the relative form, including inside reified fact
  subjects/objects and `ontfs:source` values. Fact IDs are hashes of
  `(s, p, o)` and will change; the migration must remap them and update
  `.ontfs.proposals.json` references.
- Tests: copy a graph directory to a temp location; `context` and
  `search --related-to` give identical results (modulo absolute path prefix).

**Phase 1 exit criteria:** all three tasks merged, full test suite green, a
manual run of the tagfs emulation example against the migrated format.

**Phase 1 status: complete.** Test suite and TagFS emulation checks pass.

---

## Phase 2 — Modelling expressiveness

Goal: ONTFS can express the localkb ontology rules natively.

### 2.1 Entity lifecycle separate from fact lifecycle (P2)

**Status: complete.**

- Namespace additions (`namespaces.py` / ONTFS vocabulary):
  `ontfs:entityStatus` (functional datatype property) with allowed values
  documented (`active`, `verified`, `experimental`, `stale`, `superseded`,
  `deprecated` — consumers may define their own via SHACL in 2.3);
  `ontfs:supersedes` (object property; `ontfs:supersededBy` as
  `owl:inverseOf`).
- `core.py`: `set_entity_status(entity, status, reason=None)` (records a reified
  fact like any other assertion, so it has provenance) and
  `supersede(new, old, ...)` which links and sets the old entity's status.
- `context()`: return `entity_status` alongside `facts`; add
  `include_superseded=False` default that drops superseded neighbours.
- CLI / MCP: `entity-status`, `supersede` commands/tools.
- Tests: status changes are single-valued; superseded entity hidden by default
  and visible with the flag.

### 2.2 Boolean tag-expression selection (P7)

**Status: complete; the TagFS wrapper now uses the selector.**

- New module `ontfs/select.py`:
  - tokenizer + recursive-descent parser for `& | ! ( )` over concept names
    (prefixed or bare labels resolved via `skos:prefLabel`/`altLabel`).
  - compile to SPARQL using `?r <tagPredicate> ?t . ?t skos:broader* <C>` per
    leaf; `!` via `FILTER NOT EXISTS`.
  - tag predicate configurable (default `ontfs:hasTag`, matching the emulation).
- CLI: `ontfs select "<expr>" [--predicate ...] [--limit N]`; MCP tool `select`.
- Update `examples/tagfs_emulation/tagfs_wrapper.py` `lsresources` to use it
  and remove the "single tags only" caveat.
- Tests: precedence, parentheses, negation, transitive hierarchy, unknown tag
  error message.

### 2.3 SHACL validation (P8)

**Status: implemented; runtime validation tests require the optional `pyshacl`
dependency and are skipped when it is unavailable.**

- `pyproject.toml`: `shacl = ["pyshacl>=0.25"]` extra.
- `ontfs/validation.py`: load shapes from `--shapes` path or
  `.ontfs.shapes.ttl` in the graph directory; run pyshacl with
  `inference="none"`; return structured violations (focus node, path, message).
- CLI: `ontfs validate [--shapes file]`.
- `validate_proposal()`: if shapes exist, apply the proposal to a copy of the
  graph and validate; violations make the proposal invalid with messages.
- Contradiction gating (P1) also honours `sh:maxCount 1` from shapes.
- Tests (skipped when pyshacl missing): cardinality rejection, `sh:in`
  allowed-values rejection, clean graph passes.

**Phase 2 exit criteria:** the localkb ontology rules (facets, exclusive
status, 2-facet minimum, max depth 3, max 12 children) can be written as a
shapes file and enforced (localkb PLAN.md, step 2).

**Phase 2 status: implementation complete.** Generic SHACL shapes can express
these constraints; pyshacl runtime enforcement is optional and was skipped in
this environment because the extra is not installed.

---

## Phase 3 — Provenance depth

### 3.1 Multiple evidence records per fact (P5)

**Status: complete; migration, aggregation, and status-history tests pass.**

- Data model:
  - keep `ontfs:fact/<hash(s,p,o)>` as the aggregate fact node (status lives
    here).
  - new `ontfs:evidence/<uuid>` nodes: `ontfs:supports <fact>`,
    `prov:wasDerivedFrom <source>`, `prov:wasAttributedTo` (agent/session),
    `prov:generatedAtTime`, `ontfs:confidence`, `ontfs:note`.
  - status changes append `ontfs:statusEvent` nodes (from, to, at, by,
    reason) to give a verification history.
- `record_fact()`: if the fact exists, add a new evidence node instead of
  adding a second `ontfs:source`/`confidence` value to the fact.
- Migration `ontfs migrate-evidence`: convert existing per-fact metadata into a
  single evidence node per fact.
- `fact_metadata()` / `context()`: return `evidence: [...]` (capped) and an
  aggregate confidence (max, plus count).
- Named graphs / TriG per session and RDF 1.2 triple terms: prototype only;
  decide after measuring rdflib support. Do not block this phase on it.
- Tests: two `remember` calls with different sources → one fact, two evidence
  records; history records each status transition.

**Phase 3 status: complete.**

---

## Phase 4 — Retrieval quality and scale

### 4.1 Index-based traversal (P9, part 1)

**Status: complete.** `context()` uses indexed adjacency lookups. The synthetic
100k-triple benchmark on the current developer environment measured about
0.00008s indexed versus 0.19s for a full scan (roughly 2,400x); rerun the
benchmark locally for environment-specific numbers.

- Replace the full-graph scan in `context()` with
  `graph.triples((node, None, None))` and `graph.triples((None, None, node))`
  per frontier node. Same output contract.
- Benchmark script `tests/bench_context.py` (not part of unit suite) with a
  synthetic 100k-triple graph; record baseline vs new latency in the PR.

### 4.2 Honest and persistent embeddings (P6)

**Status: implementation complete; cache reuse/invalidation and unchanged
hashed-vector output are covered by tests.** The optional neural backend is
implemented but its dependency/model-download path was not exercised because
the optional package is not installed in this environment.

- Rename the current mode: `--hashed` (keep `--vector` as a deprecated alias
  for one release).
- `embeddings.py`: `EmbeddingBackend` protocol (`name`, `dimensions`,
  `embed(texts) -> list[list[float]]`); `HashedBackend` (current code);
  `SentenceTransformerBackend` behind an `embed` extra.
- Persistent cache `.ontfs.vectors/` keyed by `(backend, model, content
  sha256)`; `search()` reuses cached vectors; `watch` evicts changed files.
- Tests: cache hit avoids re-embedding (mock backend counts calls); hashed
  backend output unchanged.

### 4.3 Pointer-returning budgeted recall (P10)

**Status: implemented and covered by tests for alias matching, output limits,
pointer-only responses, and superseded filtering.**

- New module `ontfs/recall.py`:
  1. Seed: match query terms against `skos:prefLabel`, `altLabel`,
     `hiddenLabel`, entity labels, and optionally `search()` text hits.
  2. Expand: `skos:narrower*` for concept seeds; collect resources linked to
     seeds.
  3. Rank: reciprocal-rank fusion of lexical rank, graph-proximity rank, and
     (optional) vector rank; optional personalized PageRank from seeds
     (pure-Python power iteration; networkx not required).
  4. Filter: drop retracted facts and superseded entities (2.1) by default.
  5. Output: `{query, results: [{uri, path, label, summary, why}], stats}`
     capped by `--limit` (default 6); `stats` includes approximate output
     tokens and a `capped` flag. `summary` comes from a configurable predicate
     (e.g. `dcterms:abstract`), never file content.
- CLI `ontfs recall`; MCP tool `recall`.
- Tests: output length ≤ limit; no file contents present; altLabel synonym
  query hits; superseded entity excluded.

**Phase 4 status: complete except for the explicitly deferred conditional
store backend (4.4).**

### 4.4 Persistent store backend (P9, part 2) — optional

**Status: deferred by its entry condition.** The benchmark isolates traversal
and shows indexed traversal is fast; it does not measure Turtle parse time or
show parsing dominates realistic workloads. No persistent backend or pyoxigraph
dependency has been added pending an end-to-end parse/profile benchmark.

- Abstract `RDFHandler` storage behind a small interface; add a pyoxigraph
  implementation behind a `store` extra; `.ontfs.ttl` import/export kept so
  graphs stay portable and diffable.
- Only start if 4.1 benchmarks show parse time is the dominant cost for
  realistic graphs.

---

## Dependency summary

```
P1 ─┐
P4 ─┼─▶ Phase 1 exit ─▶ P2 ─┬─▶ P8
P3 ─┘                  P7 ──┘
P5 (Phase 3) — after Phase 1
4.1 ─▶ 4.2 ─▶ 4.3 (P10; uses P2 to filter superseded entities)
4.4 (only if 4.1 benchmarks justify)
```

localkb needs Phase 1 and 2.1–2.3 before its graph compiler, 4.3 before
recall cut-over, and Phase 3 for its richer-capture step.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| URI migration (P3) changes fact IDs and breaks proposal references | `migrate-uris` remaps IDs and proposals; `--dry-run`; back up `.ontfs.ttl` first |
| Lock semantics differ across OS / network filesystems | Document supported platforms; tests on Linux; fail loudly if locking unavailable |
| pyshacl / sentence-transformers weight | Optional extras; core stays rdflib-only |
| MCP tool schemas add per-session context cost | Keep the MCP tool set small and well-described |
| Reification + evidence nodes inflate graph size | Measure in 4.1 benchmark; named graphs / triple terms as follow-up |
