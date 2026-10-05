import argparse
import json
import sys
from ontfs.core import OntFS

def main():
    parser = argparse.ArgumentParser(description="OntFS: Ontology Knowledge Graph CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    init_parser = subparsers.add_parser("init", help="Initialize a new OntFS graph in the current directory")

    # Add-Relation
    addrel_parser = subparsers.add_parser("add-relation", help="Define a new ontology relation (property)")
    addrel_parser.add_argument("uri", help="The URI or prefixed name for the relation (e.g. custom:dependsOn)")
    addrel_parser.add_argument("--type", choices=["object", "datatype"], help="Type of property")
    addrel_parser.add_argument("--transitive", action="store_true", help="Mark as owl:TransitiveProperty")
    addrel_parser.add_argument("--symmetric", action="store_true", help="Mark as owl:SymmetricProperty")
    addrel_parser.add_argument("--functional", action="store_true", help="Mark as owl:FunctionalProperty")
    addrel_parser.add_argument("--subprop-of", help="URI this relation is a sub-property of (rdfs:subPropertyOf)")
    addrel_parser.add_argument("--inverse", help="URI that is the inverse of this relation (owl:inverseOf)")


    # Add-Relations (Batch)
    addrels_parser = subparsers.add_parser("add-relations", help="Define multiple ontology relations from a JSON file")
    addrels_parser.add_argument("file", help="Path to a JSON file containing a list of relation objects")

    # Link
    link_parser = subparsers.add_parser("link", help="Link two entities")
    link_parser.add_argument("subject", help="Subject URI or local file path")
    link_parser.add_argument("predicate", help="Predicate URI (the relation)")
    link_parser.add_argument("object", help="Object URI or local file path")
    link_parser.add_argument("--literal", action="store_true", help="Treat the object as a literal string instead of a URI")
    link_parser.add_argument("--source", help="Evidence file or URL for this fact")
    link_parser.add_argument("--confidence", type=float, help="Confidence score between 0 and 1")
    link_parser.add_argument("--asserted-by", help="Agent or user asserting the fact")
    link_parser.add_argument("--note", help="Short explanation for the assertion")
    link_parser.add_argument("--observed-at", help="Observation timestamp in ISO-8601 format")
    link_parser.add_argument("--expires-at", help="ISO-8601 time after which the fact becomes stale")


    # Batch-Link
    batchlink_parser = subparsers.add_parser("batch-link", help="Link multiple entities from a JSON file")
    batchlink_parser.add_argument("file", help="Path to a JSON file containing a list of link objects")

    # Batch-Unlink
    batchunlink_parser = subparsers.add_parser("batch-unlink", help="Unlink multiple entities from a JSON file")
    batchunlink_parser.add_argument("file", help="Path to a JSON file containing a list of unlink objects")

    # Unlink
    unlink_parser = subparsers.add_parser("unlink", help="Unlink two entities")
    unlink_parser.add_argument("subject", help="Subject URI or local file path")
    unlink_parser.add_argument("predicate", help="Predicate URI")
    unlink_parser.add_argument("object", help="Object URI or local file path")

    # Query
    query_parser = subparsers.add_parser("query", help="Execute a raw SPARQL query against the graph")
    query_parser.add_argument("query_str", help="The SPARQL query string")

    fact_parser = subparsers.add_parser("fact", help="Show a fact and its lifecycle metadata")
    fact_parser.add_argument("fact_id")
    status_parser = subparsers.add_parser("fact-status", help="Change a fact lifecycle status")
    status_parser.add_argument("fact_id")
    status_parser.add_argument("status", choices=["asserted", "verified", "stale", "retracted", "disputed"])
    status_parser.add_argument("--reason")
    refresh_parser = subparsers.add_parser("refresh-facts", help="Mark expired facts as stale")
    migrate_parser = subparsers.add_parser("migrate-uris", help="Convert local file URIs to relocatable graph IDs")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Report changes without saving")
    validate_parser = subparsers.add_parser("validate", help="Validate the graph against SHACL shapes")
    validate_parser.add_argument("--shapes", help="Shapes Turtle file (default: .ontfs.shapes.ttl)")
    evidence_parser = subparsers.add_parser("migrate-evidence", help="Move legacy fact metadata to evidence records")
    contradictions_parser = subparsers.add_parser("contradictions", help="Find conflicting facts")
    contradictions_parser.add_argument("--mark", action="store_true", help="Mark conflicting facts as disputed")

    context_parser = subparsers.add_parser(
        "context", help="Return bounded JSON context around an entity for an agent"
    )
    context_parser.add_argument("entity", help="Entity URI or local file path")
    context_parser.add_argument("--depth", type=int, default=1, help="Graph traversal depth (default: 1)")
    context_parser.add_argument("--limit", type=int, default=50, help="Maximum facts to return (default: 50)")
    context_parser.add_argument("--include-superseded", action="store_true")

    entity_status_parser = subparsers.add_parser("entity-status", help="Set an entity lifecycle status")
    entity_status_parser.add_argument("entity")
    entity_status_parser.add_argument("status", choices=["active", "verified", "experimental", "stale", "superseded", "deprecated"])
    entity_status_parser.add_argument("--reason")
    supersede_parser = subparsers.add_parser("supersede", help="Mark one entity as superseded by another")
    supersede_parser.add_argument("new_entity")
    supersede_parser.add_argument("old_entity")
    supersede_parser.add_argument("--source")
    supersede_parser.add_argument("--note")

    search_parser = subparsers.add_parser(
        "search", help="Search text and boost graph-related files"
    )
    search_parser.add_argument("query")
    search_parser.add_argument("--path", default=".")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.add_argument("--related-to", help="Entity whose graph neighborhood should be boosted")
    search_parser.add_argument("--depth", type=int, default=1)
    search_parser.add_argument("--vector", "--hashed", dest="vector", action="store_true", help="Enable hashed-vector ranking (--vector is a compatibility alias)")
    search_parser.add_argument("--embedding-backend", choices=["hashed", "sentence-transformers"], default="hashed")
    search_parser.add_argument("--embedding-model", help="Sentence Transformers model name")
    search_parser.add_argument("--embedding-dimensions", type=int, default=256)

    select_parser = subparsers.add_parser("select", help="Select tagged resources with a boolean expression")
    select_parser.add_argument("expression")
    select_parser.add_argument("--predicate", default="ontfs:hasTag")
    select_parser.add_argument("--limit", type=int, default=100)

    recall_parser = subparsers.add_parser("recall", help="Return budgeted graph pointers for an agent")
    recall_parser.add_argument("query")
    recall_parser.add_argument("--limit", type=int, default=6)
    recall_parser.add_argument("--max-tokens", type=int, default=1200)
    recall_parser.add_argument("--summary-predicate", default="dcterms:abstract")
    recall_parser.add_argument("--no-text-search", action="store_true")
    recall_parser.add_argument("--vector", action="store_true")

    scan_parser = subparsers.add_parser(
        "scan", help="Index Python files, imports, and Git context for agents"
    )
    scan_parser.add_argument("path", nargs="?", default=".", help="Directory or Python file to scan")
    scan_parser.add_argument("--no-git", action="store_true", help="Do not record Git commit and branch")

    watch_parser = subparsers.add_parser(
        "watch", help="Poll Python files and rescan when they change"
    )
    watch_parser.add_argument("path", nargs="?", default=".")
    watch_parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds")
    watch_parser.add_argument("--iterations", type=int, help="Polling cycles; omit to watch continuously")
    watch_parser.add_argument("--no-git", action="store_true", help="Do not record Git commit and branch")

    propose_parser = subparsers.add_parser(
        "propose-link", help="Create a pending link proposal without changing the graph"
    )
    propose_parser.add_argument("subject")
    propose_parser.add_argument("predicate")
    propose_parser.add_argument("object")
    propose_parser.add_argument("--literal", action="store_true")
    propose_parser.add_argument("--source")
    propose_parser.add_argument("--confidence", type=float)
    propose_parser.add_argument("--asserted-by")
    propose_parser.add_argument("--note")
    propose_parser.add_argument("--observed-at")
    propose_parser.add_argument("--expires-at")

    proposals_parser = subparsers.add_parser("proposals", help="List pending or completed proposals")
    proposals_parser.add_argument("--status", choices=["proposed", "committed", "rejected"])

    validate_parser = subparsers.add_parser("validate-proposal", help="Validate a pending proposal")
    validate_parser.add_argument("proposal_id")

    commit_parser = subparsers.add_parser("commit-proposal", help="Validate and apply a pending proposal")
    commit_parser.add_argument("proposal_id")

    reject_parser = subparsers.add_parser("reject-proposal", help="Reject a pending proposal")
    reject_parser.add_argument("proposal_id")
    reject_parser.add_argument("--reason")

    args = parser.parse_args()
    ontfs = OntFS()

    if args.command == "init":
        ontfs.init()
    elif args.command == "add-relation":
        ontfs.add_relation(
            args.uri, 
            rel_type=args.type, 
            is_transitive=args.transitive, 
            is_symmetric=args.symmetric, 
            subprop_of=args.subprop_of, 
            inverse_of=args.inverse,
            functional=args.functional
        )
    elif args.command == "add-relations":
        ontfs.add_relations(args.file)
    elif args.command == "link":
        if any((args.source, args.confidence is not None, args.asserted_by, args.note, args.observed_at, args.expires_at)):
            ontfs.remember(
                args.subject, args.predicate, args.object,
                obj_is_literal=args.literal, source=args.source,
                confidence=args.confidence, asserted_by=args.asserted_by,
                note=args.note, observed_at=args.observed_at, expires_at=args.expires_at,
            )
            print(f"Linked with evidence: {args.subject} -[{args.predicate}]-> {args.object}")
        else:
            ontfs.link(args.subject, args.predicate, args.object, obj_is_literal=args.literal)
    elif args.command == "batch-link":
        ontfs.batch_links(args.file)
    elif args.command == "unlink":
        ontfs.unlink(args.subject, args.predicate, args.object)
    elif args.command == "batch-unlink":
        ontfs.batch_unlinks(args.file)
    elif args.command == "query":
        ontfs.query(args.query_str)
    elif args.command == "fact":
        try:
            print(json.dumps(ontfs.fact(args.fact_id), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "fact-status":
        try:
            print(json.dumps(ontfs.set_fact_status(args.fact_id, args.status, args.reason), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "refresh-facts":
        print(json.dumps({"stale": ontfs.refresh_stale()}, indent=2))
    elif args.command == "migrate-uris":
        try:
            print(json.dumps(ontfs.migrate_uris(dry_run=args.dry_run), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "validate":
        try:
            result = ontfs.validate(args.shapes)
            print(json.dumps(result, indent=2))
            if not result["conforms"]:
                sys.exit(2)
        except RuntimeError as e:
            parser.error(str(e))
    elif args.command == "migrate-evidence":
        print(json.dumps({"facts_migrated": ontfs.migrate_evidence()}, indent=2))
    elif args.command == "contradictions":
        print(json.dumps(ontfs.contradictions(mark=args.mark), indent=2))
    elif args.command == "entity-status":
        try:
            print(json.dumps({"entity": args.entity, "status": ontfs.set_entity_status(
                args.entity, args.status, args.reason
            )}, indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "supersede":
        try:
            print(json.dumps({"fact_id": ontfs.supersede(
                args.new_entity, args.old_entity, source=args.source, note=args.note
            )}, indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "context":
        try:
            print(json.dumps(ontfs.context(
                args.entity, depth=args.depth, limit=args.limit,
                include_superseded=args.include_superseded,
            ), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "search":
        try:
            print(json.dumps(ontfs.search(
                args.query, path=args.path, limit=args.limit,
                related_to=args.related_to, depth=args.depth, vector=args.vector,
                embedding_dimensions=args.embedding_dimensions,
                embedding_backend=args.embedding_backend,
                embedding_model=args.embedding_model,
            ), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "select":
        try:
            print(json.dumps(ontfs.select(
                args.expression, predicate=args.predicate, limit=args.limit
            ), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "recall":
        try:
            print(json.dumps(ontfs.recall(
                args.query, limit=args.limit, max_tokens=args.max_tokens,
                summary_predicate=args.summary_predicate,
                search_text=not args.no_text_search, vector=args.vector,
            ), indent=2))
        except (ValueError, RuntimeError) as e:
            parser.error(str(e))
    elif args.command == "scan":
        try:
            print(json.dumps(ontfs.scan(args.path, include_git=not args.no_git), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "watch":
        try:
            results = ontfs.watch(
                args.path, interval=args.interval, iterations=args.iterations,
                include_git=not args.no_git,
            )
            print(json.dumps({"scans": results, "watching": args.iterations is None}, indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "propose-link":
        try:
            print(json.dumps(ontfs.propose_link(
                args.subject, args.predicate, args.object,
                obj_is_literal=args.literal, source=args.source,
                confidence=args.confidence, asserted_by=args.asserted_by,
                note=args.note, observed_at=args.observed_at, expires_at=args.expires_at,
            ), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "proposals":
        print(json.dumps(ontfs.list_proposals(status=args.status), indent=2))
    elif args.command == "validate-proposal":
        try:
            print(json.dumps(ontfs.validate_proposal(args.proposal_id), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "commit-proposal":
        try:
            print(json.dumps(ontfs.commit_proposal(args.proposal_id), indent=2))
        except ValueError as e:
            parser.error(str(e))
    elif args.command == "reject-proposal":
        try:
            print(json.dumps(ontfs.reject_proposal(args.proposal_id, args.reason), indent=2))
        except ValueError as e:
            parser.error(str(e))
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
