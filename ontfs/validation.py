"""Optional SHACL validation for an ONTFS RDF graph."""

from pathlib import Path

from rdflib import Graph, URIRef, RDF
from rdflib.namespace import SH


DEFAULT_SHAPES = ".ontfs.shapes.ttl"


def load_shapes(directory, shapes_path=None):
    path = Path(shapes_path) if shapes_path else Path(directory) / DEFAULT_SHAPES
    if not path.is_absolute():
        path = Path(directory) / path
    if not path.exists():
        return None, path
    shapes = Graph()
    shapes.parse(path, format="turtle")
    return shapes, path


def functional_paths(shapes):
    """Return SHACL paths whose maximum count is one."""
    if shapes is None:
        return set()
    result = set()
    for shape in set(shapes.subjects(SH.maxCount, None)):
        maximum = next(shapes.objects(shape, SH.maxCount), None)
        path = next(shapes.objects(shape, SH.path), None)
        try:
            if path is not None and int(maximum) <= 1:
                result.add(path)
        except (TypeError, ValueError):
            continue
    return result


def validate_graph(data_graph, directory, shapes_path=None):
    shapes, path = load_shapes(directory, shapes_path)
    if shapes is None:
        return {
            "conforms": True,
            "shapes_loaded": False,
            "shapes_path": str(path),
            "violations": [],
        }
    try:
        from pyshacl import validate
    except ImportError as error:
        raise RuntimeError("SHACL validation requires the optional `ontfs[shacl]` extra") from error
    conforms, report, _ = validate(
        data_graph=data_graph, shacl_graph=shapes, inference="none",
    )
    violations = []
    for result in report.subjects(RDF.type, SH.ValidationResult):
        focus = next(report.objects(result, SH.focusNode), None)
        path_node = next(report.objects(result, SH.resultPath), None)
        message = next(report.objects(result, SH.resultMessage), None)
        value = next(report.objects(result, SH.value), None)
        source_shape = next(report.objects(result, SH.sourceShape), None)
        if focus is not None:
            constraint = next(report.objects(result, SH.sourceConstraintComponent), None)
            value_count = None
            if constraint == SH.MaxCountConstraintComponent and isinstance(path_node, URIRef):
                value_count = len(set(data_graph.objects(focus, path_node)))
            violations.append({
                "focus_node": str(focus),
                "path": str(path_node) if path_node is not None else None,
                "message": str(message) if message is not None else "SHACL constraint violation",
                "source_constraint": str(constraint) if constraint is not None else None,
                "source_shape": str(source_shape) if isinstance(source_shape, URIRef) else None,
                "value": str(value) if value is not None else None,
                "value_count": value_count,
            })
    return {
        "conforms": bool(conforms),
        "shapes_loaded": True,
        "shapes_path": str(path),
        "violations": violations,
    }
