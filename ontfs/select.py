"""Boolean selection over tagged resources."""

import re

from rdflib import URIRef
from rdflib.namespace import RDFS, SKOS


TOKEN = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"|([&|!()]|[^\s&|!()]+)')


class ExpressionParser:
    def __init__(self, expression):
        self.tokens = [quoted if quoted else bare
                       for quoted, bare in TOKEN.findall(expression)]
        self.position = 0
        if not self.tokens:
            raise ValueError("selection expression is empty")

    def parse(self):
        tree = self.parse_or()
        if self.position != len(self.tokens):
            raise ValueError(f"unexpected token: {self.tokens[self.position]}")
        return tree

    def accept(self, token):
        if self.position < len(self.tokens) and self.tokens[self.position] == token:
            self.position += 1
            return True
        return False

    def parse_or(self):
        node = self.parse_and()
        while self.accept("|"):
            node = ("or", node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_unary()
        while self.accept("&"):
            node = ("and", node, self.parse_unary())
        return node

    def parse_unary(self):
        if self.accept("!"):
            return ("not", self.parse_unary())
        if self.accept("("):
            node = self.parse_or()
            if not self.accept(")"):
                raise ValueError("missing closing parenthesis")
            return node
        if self.position >= len(self.tokens) or self.tokens[self.position] in {"&", "|", ")"}:
            raise ValueError("expected a concept name")
        token = self.tokens[self.position]
        self.position += 1
        return ("concept", token)


def _resolve_concept(ontfs, label):
    graph = ontfs.graph.graph
    if ":" in label:
        candidate = ontfs.graph.resolve_uri(label)
        if (candidate, None, None) in graph:
            return candidate
    custom_tag = ontfs.graph.resolve_uri("custom:tag:" + label)
    if (custom_tag, None, None) in graph:
        return custom_tag
    wanted = label.casefold()
    matches = set()
    for predicate in (SKOS.prefLabel, SKOS.altLabel, SKOS.hiddenLabel, RDFS.label):
        for subject, value in graph.subject_objects(predicate):
            if str(value).casefold() == wanted:
                matches.add(subject)
    if not matches:
        raise ValueError(f"unknown tag or concept: {label}")
    if len(matches) > 1:
        raise ValueError(f"ambiguous tag or concept label: {label}")
    return next(iter(matches))


def select(ontfs, expression, predicate="ontfs:hasTag", limit=100):
    if limit <= 0:
        raise ValueError("limit must be positive")
    tree = ExpressionParser(expression).parse()
    graph = ontfs.graph.graph
    tag_predicate = ontfs.graph.resolve_uri(predicate)
    memberships = {}
    universe = set()
    for resource, tag in graph.subject_objects(tag_predicate):
        universe.add(resource)
        ancestors = set()
        pending = [tag]
        while pending:
            current = pending.pop()
            if current in ancestors:
                continue
            ancestors.add(current)
            pending.extend(graph.objects(current, SKOS.broader))
        memberships.setdefault(resource, set()).update(ancestors)

    def evaluate(node):
        operation = node[0]
        if operation == "concept":
            concept = _resolve_concept(ontfs, node[1])
            return {resource for resource, tags in memberships.items() if concept in tags}
        if operation == "not":
            return universe - evaluate(node[1])
        left = evaluate(node[1])
        right = evaluate(node[2])
        return left & right if operation == "and" else left | right

    resources = sorted(evaluate(tree), key=str)
    return {
        "expression": expression,
        "predicate": str(tag_predicate),
        "total": len(resources),
        "capped": len(resources) > limit,
        "resources": [
            {"uri": str(resource), "path": ontfs.graph.to_path(resource)}
            for resource in resources[:limit]
        ],
    }
