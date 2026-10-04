import argparse
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

    context_parser = subparsers.add_parser(
        "context", help="Return bounded JSON context around an entity for an agent"
    )
    context_parser.add_argument("entity", help="Entity URI or local file path")
    context_parser.add_argument("--depth", type=int, default=1, help="Graph traversal depth (default: 1)")
    context_parser.add_argument("--limit", type=int, default=50, help="Maximum facts to return (default: 50)")

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
            inverse_of=args.inverse
        )
    elif args.command == "add-relations":
        ontfs.add_relations(args.file)
    elif args.command == "link":
        if any((args.source, args.confidence is not None, args.asserted_by, args.note, args.observed_at)):
            ontfs.remember(
                args.subject, args.predicate, args.object,
                obj_is_literal=args.literal, source=args.source,
                confidence=args.confidence, asserted_by=args.asserted_by,
                note=args.note, observed_at=args.observed_at,
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
    elif args.command == "context":
        try:
            print(ontfs.context_json(args.entity, depth=args.depth, limit=args.limit))
        except ValueError as e:
            parser.error(str(e))
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
