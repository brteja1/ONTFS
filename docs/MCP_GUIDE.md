# ONTFS MCP Guide

ONTFS provides an optional [Model Context Protocol](https://modelcontextprotocol.io/)
server for agents that need graph memory, repository context, and safe
knowledge updates.

## Installation

Install the optional MCP extra:

```bash
pip install -e '.[mcp]'
```

Start a server scoped to the current directory:

```bash
ontfs-mcp --directory .
```

The default transport is `stdio`, which is appropriate for local agent
hosts. The server also accepts `--transport sse` and
`--transport streamable-http` when an MCP client requires a network transport.

## Exposed tools

| Tool | Purpose |
| --- | --- |
| `context` | Return bounded graph facts and provenance around an entity. |
| `search` | Search local text with lexical, graph, and optional vector ranking. |
| `recall` | Return token-budgeted graph pointers and ontology summaries, without file bodies. |
| `select` | Select resources with Boolean expressions over hierarchical tags. |
| `scan` | Index Python files, imports, and Git provenance. |
| `validate` | Validate the graph against configured SHACL shapes. |
| `propose_link` | Stage a relationship without changing the graph. |
| `validate_proposal` | Check a pending proposal before mutation. |
| `commit_proposal` | Apply a validated proposal. |
| `set_fact_status` | Mark a fact asserted, verified, stale, disputed, or retracted. |
| `contradictions` | Find or mark conflicting facts. |

## Safe mutation pattern

Agents should use the proposal workflow for writes:

1. Call `propose_link` with evidence and confidence.
2. Call `validate_proposal` using the returned proposal ID.
3. Ask for approval or apply local policy.
4. Call `commit_proposal` only after validation and approval.

The server exposes one directory per process. It does not grant access to a
separate graph directory through tool arguments; start another scoped server
when a different graph is required.

## Embedding behavior

The `search` tool can enable `vector=true`. ONTFS uses deterministic hashed
embeddings by default, so no model download is required. Vectors are cached in
the graph directory and the watcher evicts changed-file entries. The CLI also
supports `sentence-transformers` with the optional `.[embed]` extra; vector
search returns rankings, while `recall` is the pointer-only bounded tool.
