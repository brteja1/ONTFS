# ONTFS Agent-Native Knowledge Plan

## Goal

Make ONTFS useful to AI agents as a local, evidence-backed memory and context
layer, while continuing to use RDF and `rdflib` as the storage/query foundation.

## Milestone 1 (this change)

1. Preserve the asserted RDF triple, but also record a stable fact identifier.
2. Attach optional provenance, confidence, timestamp, and note metadata to facts.
3. Add an agent-friendly `context` command that returns bounded JSON context for
   an entity, including neighboring facts and their evidence.
4. Add validation for confidence values and context depth/limit.
5. Keep existing CLI and Python APIs compatible, including the existing batch
   commands.

## Follow-up milestones

- Git-aware repository scanning and file watching.
- Fact lifecycle: proposed, verified, stale, retracted, and contradiction views.
- Dry-run/proposal/commit mutation workflow with audit history.
- Hybrid graph, text, and vector retrieval.
- MCP and higher-level Python APIs for agent runtimes.

## Success criteria

- An agent can add a fact with its source and confidence.
- An agent can retrieve compact, explainable context without writing SPARQL.
- Existing RDF/SPARQL consumers continue to see the original direct triples.
- Tests cover metadata persistence, context retrieval, and invalid input.
