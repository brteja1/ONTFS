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

## Milestone 5 (this change)

1. Add asserted, verified, stale, disputed, and retracted fact states.
2. Mark facts stale when their expiration time is reached.
3. Preserve retracted fact history while removing it from active context.
4. Detect and optionally mark conflicting object values as disputed.

## Milestone 6 (this change)

1. Search local text files with bounded lexical matching and snippets.
2. Boost results connected to a requested graph neighborhood.
3. Return compact JSON suitable for agent context selection.

## Milestone 7 (this change)

1. Add deterministic local vector embeddings without a mandatory ML dependency.
2. Combine cosine similarity with lexical and graph relevance scores.
3. Expose vector ranking controls through the Python API and CLI.

## Milestone 8 (this change)

1. Expose context, search, scanning, proposals, and lifecycle operations as
   optional MCP tools.
2. Scope each MCP server instance to one ONTFS directory.
3. Keep MCP optional so the core CLI and Python package do not require it.

## Follow-up milestones

- Pluggable neural embedding backends and persistent vector indexes.

## Success criteria

- An agent can add a fact with its source and confidence.
- An agent can retrieve compact, explainable context without writing SPARQL.
- Existing RDF/SPARQL consumers continue to see the original direct triples.
- Tests cover metadata persistence, context retrieval, and invalid input.
