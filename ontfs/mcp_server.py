"""Optional MCP server exposing ONTFS as agent tools."""

import argparse
from typing import Optional

from ontfs.core import OntFS


def create_server(directory: str = "."):
    """Create an MCP server scoped to one ONTFS directory."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "MCP support is optional; install it with `pip install 'ontfs[mcp]'`"
        ) from error

    ontfs = OntFS(directory)
    server = FastMCP(
        "ontfs",
        instructions=(
            "Use ONTFS for evidence-backed graph context, safe proposals, "
            "repository scanning, and hybrid search. Keep mutations proposed "
            "until they have been validated."
        ),
    )

    @server.tool(description="Return bounded, explainable graph context around an entity.")
    def context(entity: str, depth: int = 1, limit: int = 50,
                include_superseded: bool = False) -> dict:
        return ontfs.context(
            entity, depth=depth, limit=limit,
            include_superseded=include_superseded,
        )

    @server.tool(description="Search local text with optional graph and vector ranking.")
    def search(query: str, path: str = ".", limit: int = 20,
               related_to: Optional[str] = None, depth: int = 1,
               vector: bool = False, embedding_dimensions: int = 256) -> dict:
        return ontfs.search(
            query, path=path, limit=limit, related_to=related_to,
            depth=depth, vector=vector, embedding_dimensions=embedding_dimensions,
        )

    @server.tool(description="Scan Python files, imports, and Git provenance.")
    def scan(path: str = ".", include_git: bool = True) -> dict:
        return ontfs.scan(path, include_git=include_git)

    @server.tool(description="Select resources using Boolean expressions over hierarchical tags.")
    def select(expression: str, predicate: str = "ontfs:hasTag", limit: int = 100) -> dict:
        return ontfs.select(expression, predicate=predicate, limit=limit)

    @server.tool(description="Return budgeted graph pointers and summaries without file contents.")
    def recall(query: str, limit: int = 6, max_tokens: int = 1200,
               search_text: bool = True, vector: bool = False) -> dict:
        return ontfs.recall(query, limit=limit, max_tokens=max_tokens,
                            search_text=search_text, vector=vector)

    @server.tool(description="Create a pending link proposal without changing the graph.")
    def propose_link(subject: str, predicate: str, object: str,
                     literal: bool = False, source: Optional[str] = None,
                     confidence: Optional[float] = None,
                     asserted_by: Optional[str] = None,
                     note: Optional[str] = None,
                     observed_at: Optional[str] = None,
                     expires_at: Optional[str] = None) -> dict:
        return ontfs.propose_link(
            subject, predicate, object, obj_is_literal=literal, source=source,
            confidence=confidence, asserted_by=asserted_by, note=note,
            observed_at=observed_at, expires_at=expires_at,
        )

    @server.tool(description="Validate a pending proposal by ID.")
    def validate_proposal(proposal_id: str) -> dict:
        return ontfs.validate_proposal(proposal_id)

    @server.tool(description="Commit a validated pending proposal by ID.")
    def commit_proposal(proposal_id: str) -> dict:
        return ontfs.commit_proposal(proposal_id)

    @server.tool(description="Change a fact lifecycle status.")
    def set_fact_status(fact_id: str, status: str,
                        reason: Optional[str] = None) -> dict:
        return ontfs.set_fact_status(fact_id, status, reason=reason)

    @server.tool(description="Set an entity lifecycle status.")
    def set_entity_status(entity: str, status: str,
                          reason: Optional[str] = None) -> dict:
        return {"entity": entity, "status": ontfs.set_entity_status(entity, status, reason)}

    @server.tool(description="Record that one entity supersedes another.")
    def supersede(new_entity: str, old_entity: str,
                  source: Optional[str] = None,
                  note: Optional[str] = None) -> dict:
        return {"fact_id": ontfs.supersede(new_entity, old_entity, source, note)}

    @server.tool(description="Find conflicting object values for subject/predicate pairs.")
    def contradictions(mark: bool = False) -> list:
        return ontfs.contradictions(mark=mark)

    @server.tool(description="Validate the active graph against configured SHACL shapes.")
    def validate(shapes_path: Optional[str] = None) -> dict:
        return ontfs.validate(shapes_path)

    return server


def main():
    parser = argparse.ArgumentParser(description="ONTFS MCP server")
    parser.add_argument("--directory", default=".", help="ONTFS directory to expose")
    parser.add_argument(
        "--transport", choices=["stdio", "sse", "streamable-http"], default="stdio",
    )
    args = parser.parse_args()
    create_server(args.directory).run(args.transport)


if __name__ == "__main__":
    main()
