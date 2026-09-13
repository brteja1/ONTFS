# Emulating TagFS with OntFS

OntFS is a generalized knowledge graph, whereas HTFS (`tagfs`) is a strict bipartite hierarchical tagging system. 

Because a bipartite graph is just a subset of a generalized graph, we can perfectly emulate `tagfs` using OntFS and the SKOS ontology. 

To demonstrate this, we have provided a complete Python emulation layer: `tagfs_wrapper.py`.

## The Emulation Layer (`tagfs_wrapper.py`)

This wrapper script exposes the exact same CLI API as the original `tagfs` tool, but it achieves this by calling directly into the `OntFS` core library (`ontfs.core`).

### The Mapping Strategy

Inside the wrapper, `tagfs` concepts are dynamically translated into `ontfs` triples:

| Concept in TagFS | Emulation in OntFS (RDF Triple) |
|------------------|---------------------------------|
| A Tag | A custom URI: `custom:tag:Project` |
| Tag Hierarchy (`Project/Alpha`) | `<custom:tag:Alpha> <skos:broader> <custom:tag:Project>` |
| Tagging a File | `<file:///path.pdf> <ontfs:hasTag> <custom:tag:Alpha>` |

### Usage Examples

You can run the wrapper exactly like the original `tagfs`:

**1. Initialize the graph**
```bash
./tagfs_wrapper.py init
```
*(Under the hood, this calls `ontfs.init()` and defines the `ontfs:hasTag` relation).*

**2. Create tag hierarchies**
```bash
./tagfs_wrapper.py addtags "Project/Alpha/Design"
```
*(This parses the path and links Design -> Alpha, and Alpha -> Project using `skos:broader`).*

**3. Tag resources**
```bash
./tagfs_wrapper.py tagresource ./spec.md Design
```
*(Links the file to the Design tag via `ontfs:hasTag`).*

**4. Query files transitively**
```bash
./tagfs_wrapper.py lsresources Project
```
*(This translates into a SPARQL query that finds files tagged with `Project` **OR** any tag that has a `skos:broader*` path leading back to `Project`, natively executing a transitive closure search).*
