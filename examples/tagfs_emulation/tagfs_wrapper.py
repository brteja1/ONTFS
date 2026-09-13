#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import ontfs without installing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ontfs.core import OntFS

# Define the standard URIs used for our TagFS emulation
TAG_PREFIX = "tag:"
HAS_TAG_RELATION = "ontfs:hasTag"
BROADER_RELATION = "skos:broader"

class TagFSWrapper:
    """
    A layer that exposes the traditional TagFS API by calling into
    the generalized OntFS knowledge graph.
    """
    def __init__(self, directory: str = "."):
        self.ontfs = OntFS(directory)
        
    def init(self):
        self.ontfs.init()
        # Define the ontfs:hasTag relation if not already defined
        self.ontfs.add_relation(HAS_TAG_RELATION, rel_type="object")

    def _parse_hierarchy(self, tag_path: str):
        """Helper to split 'Project/Alpha/Design' into individual tags."""
        return [t for t in tag_path.split("/") if t]

    def addtags(self, *tag_paths: str):
        """
        tagfs addtags "Project/Alpha"
        Creates the hierarchy by linking Alpha to Project via skos:broader
        """
        for path in tag_paths:
            parts = self._parse_hierarchy(path)
            for i in range(1, len(parts)):
                parent = f"{TAG_PREFIX}{parts[i-1]}"
                child = f"{TAG_PREFIX}{parts[i]}"
                # In SKOS, the child has a broader relation to the parent
                self.ontfs.link(child, BROADER_RELATION, parent)
        print(f"Added tags: {', '.join(tag_paths)}")

    def linktags(self, child_tag: str, parent_tag: str):
        """
        tagfs linktags "Research" "Project"
        Links an existing tag to a new parent.
        """
        child = f"{TAG_PREFIX}{child_tag}"
        parent = f"{TAG_PREFIX}{parent_tag}"
        self.ontfs.link(child, BROADER_RELATION, parent)

    def tagresource(self, resource_path: str, *tags: str):
        """
        tagfs tagresource ./file.pdf Design Research
        """
        for tag in tags:
            tag_uri = f"{TAG_PREFIX}{tag}"
            self.ontfs.link(resource_path, HAS_TAG_RELATION, tag_uri)

    def untagresource(self, resource_path: str, *tags: str):
        """
        tagfs untagresource ./file.pdf Design Research
        """
        for tag in tags:
            tag_uri = f"{TAG_PREFIX}{tag}"
            self.ontfs.unlink(resource_path, HAS_TAG_RELATION, tag_uri)

    def lsresources(self, tag_expr: str):
        """
        tagfs lsresources "Project"
        Finds all resources tagged with 'Project' or any of its descendants.
        (For simplicity, this emulation currently supports single tags rather than complex boolean expressions like Project&Development).
        """
        tag_uri = f"{TAG_PREFIX}{tag_expr}"
        
        # SPARQL query: Find files that have a tag which is either the target tag
        # OR has a skos:broader path leading to the target tag.
        query = f"""
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX ontfs: <http://ontfs.example.org/core#>
        
        SELECT DISTINCT ?file WHERE {{
            ?tag skos:broader* <http://ontfs.example.org/custom#{tag_expr}> .
            ?file ontfs:hasTag ?tag .
        }}
        """
        
        try:
            results = self.ontfs.graph.query_graph(query)
            for row in results:
                # Format output to look like standard paths
                uri = str(row[0])
                if uri.startswith("file://"):
                    print(uri.replace("file://", ""))
                else:
                    print(uri)
        except Exception as e:
            print(f"Query Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="TagFS Emulation using OntFS")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize the database")
    
    addtags = subparsers.add_parser("addtags", help="Add a tag hierarchy")
    addtags.add_argument("paths", nargs="+", help="Tag paths e.g., Project/Alpha")
    
    linktags = subparsers.add_parser("linktags", help="Link child tag to parent tag")
    linktags.add_argument("child", help="Child tag")
    linktags.add_argument("parent", help="Parent tag")

    tagres = subparsers.add_parser("tagresource", help="Tag a file")
    tagres.add_argument("file", help="Path to file")
    tagres.add_argument("tags", nargs="+", help="Tags to apply")

    untagres = subparsers.add_parser("untagresource", help="Remove tags from a file")
    untagres.add_argument("file", help="Path to file")
    untagres.add_argument("tags", nargs="+", help="Tags to remove")

    lsres = subparsers.add_parser("lsresources", help="List resources for a tag")
    lsres.add_argument("tag", help="Tag to search for (supports transitive search)")

    args = parser.parse_args()
    tagfs = TagFSWrapper()

    if args.command == "init":
        tagfs.init()
    elif args.command == "addtags":
        tagfs.addtags(*args.paths)
    elif args.command == "linktags":
        tagfs.linktags(args.child, args.parent)
    elif args.command == "tagresource":
        tagfs.tagresource(args.file, *args.tags)
    elif args.command == "untagresource":
        tagfs.untagresource(args.file, *args.tags)
    elif args.command == "lsresources":
        tagfs.lsresources(args.tag)

if __name__ == "__main__":
    main()
