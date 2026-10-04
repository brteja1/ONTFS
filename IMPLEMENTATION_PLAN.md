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

## Milestone 2 (this change)

1. Create pending link proposals without mutating the graph.
2. Validate proposals before commit, including metadata constraints.
3. Commit or reject proposals through explicit commands.
4. Keep proposal status and transitions in a local audit file.

## Milestone 3 (this change)

1. Scan Python repositories for source files and imports.
2. Record Git commit and branch provenance when available.
3. Expose scan results through the CLI and agent context API.

## Milestone 4 (this change)

1. Poll Python files for changes without adding a runtime dependency.
2. Reuse the scanner when a change is detected.
3. Support bounded polling cycles for tests and automation, or continuous mode
   for development workflows.

## Follow-up milestones

- Fact lifecycle: verified, stale, retracted, and contradiction views.
- Hybrid graph, text, and vector retrieval.
- MCP and higher-level Python APIs for agent runtimes.

## Success criteria

- An agent can add a fact with its source and confidence.
- An agent can retrieve compact, explainable context without writing SPARQL.
- Existing RDF/SPARQL consumers continue to see the original direct triples.
- Tests cover metadata persistence, context retrieval, and invalid input.
