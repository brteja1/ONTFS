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

    # Link
    link_parser = subparsers.add_parser("link", help="Link two entities")
    link_parser.add_argument("subject", help="Subject URI or local file path")
    link_parser.add_argument("predicate", help="Predicate URI (the relation)")
    link_parser.add_argument("object", help="Object URI or local file path")
    link_parser.add_argument("--literal", action="store_true", help="Treat the object as a literal string instead of a URI")

    # Unlink
    unlink_parser = subparsers.add_parser("unlink", help="Unlink two entities")
    unlink_parser.add_argument("subject", help="Subject URI or local file path")
    unlink_parser.add_argument("predicate", help="Predicate URI")
    unlink_parser.add_argument("object", help="Object URI or local file path")

    # Query
    query_parser = subparsers.add_parser("query", help="Execute a raw SPARQL query against the graph")
    query_parser.add_argument("query_str", help="The SPARQL query string")

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
    elif args.command == "link":
        ontfs.link(args.subject, args.predicate, args.object, obj_is_literal=args.literal)
    elif args.command == "unlink":
        ontfs.unlink(args.subject, args.predicate, args.object)
    elif args.command == "query":
        ontfs.query(args.query_str)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
