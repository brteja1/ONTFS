# Future Roadmap

ONTFS currently provides RDF graph storage, provenance-aware facts, safe
proposals, lifecycle management, repository scanning, polling, hybrid search,
vector ranking, and an optional MCP server. The remaining roadmap is grouped
below by value and implementation scope.

## Planned milestones

### 1. Pluggable embedding backends and persistent indexes

- Support neural embedding providers such as local sentence-transformer models
  and external embedding services.
- Keep the current deterministic hashed embeddings as an offline fallback.
- Persist embeddings and search indexes instead of rebuilding them per query.
- Support index invalidation when watched files change.

### 2. Richer repository intelligence

- Resolve imports to actual local files where possible.
- Extract symbols, functions, classes, tests, documentation links, and build
  dependencies.
- Add language adapters beyond Python.
- Make scanning incremental and remove facts for deleted files.

### 3. Stronger evidence and contradiction workflows

- Preserve multiple independent evidence records for one fact.
- Add verification history rather than only the latest lifecycle status.
- Improve contradiction resolution with source priority and human/agent review.
- Add explicit fact retraction and replacement relationships.

### 4. MCP production hardening

- Add MCP resources and prompts in addition to tools.
- Add authentication and authorization for network transports.
- Add per-agent namespaces, permissions, and audit identity.
- Provide integration examples for common agent runtimes.

## Possible later work

- Multi-agent graph synchronization and conflict resolution.
- Distributed or remote graph backends.
- Token-budget-aware context compression and result reranking.
- Import/export adapters for common graph and vector-store formats.
