"""Budgeted, pointer-only retrieval from labels and graph relationships."""

import json
import re

from rdflib import Literal, URIRef
from rdflib.namespace import RDFS, SKOS

from ontfs.namespaces import ONTFS


def _is_retracted(graph, ontfs, subject, predicate, obj):
    fact = ontfs.graph.fact_uri(
        ontfs.graph.fact_identifier(subject, predicate, obj)
    )
    return str(next(graph.objects(fact, ONTFS.status), "asserted")) == "retracted"


def _internal(node):
    value = str(node)
    return value.startswith(tuple(str(ONTFS) + suffix for suffix in (
        "fact/", "evidence/", "statusEvent/"
    )))


def recall(ontfs, query, limit=6, summary_predicate="dcterms:abstract",
           search_text=True, vector=False, max_tokens=1200):
    if not query.strip():
        raise ValueError("query must not be empty")
    if limit <= 0 or max_tokens <= 0:
        raise ValueError("limit and max_tokens must be positive")
    graph = ontfs.graph.graph
    terms = {term.casefold() for term in re.findall(r"[\w-]+", query)}
    labels = (SKOS.prefLabel, SKOS.altLabel, SKOS.hiddenLabel, RDFS.label)
    seeds = {}
    for predicate in labels:
        for subject, _, label in graph.triples((None, predicate, None)):
            if not isinstance(label, Literal):
                continue
            words = {word.casefold() for word in re.findall(r"[\w-]+", str(label))}
            overlap = len(terms & words)
            if overlap:
                seeds[subject] = max(seeds.get(subject, 0), overlap / max(len(terms), 1))
    expanded = set(seeds)
    for seed in tuple(seeds):
        expanded.update(graph.objects(seed, SKOS.narrower))
        expanded.update(graph.subjects(SKOS.broader, seed))

    rank = {}
    reasons = {}
    for node in expanded:
        for subject, predicate, obj in graph.triples((None, None, node)):
            if subject == node or not isinstance(subject, URIRef) or _internal(subject):
                continue
            if _is_retracted(graph, ontfs, subject, predicate, node):
                continue
            if ontfs.graph.entity_status(subject) == "superseded":
                continue
            rank[subject] = max(rank.get(subject, 0.0), seeds.get(node, 0.0))
            reasons.setdefault(subject, set()).add(f"linked by {predicate}")
        for _, predicate, obj in graph.triples((node, None, None)):
            if isinstance(obj, URIRef) and obj != node and not _internal(obj):
                if not _is_retracted(graph, ontfs, node, predicate, obj):
                    rank[obj] = max(rank.get(obj, 0.0), seeds.get(node, 0.0))
                    reasons.setdefault(obj, set()).add(f"linked by {predicate}")

    lexical = {}
    if search_text:
        found = ontfs.search(query, limit=max(limit * 4, limit), vector=vector)
        lexical = {ontfs.graph.resolve_uri(item["path"]): 1 / (i + 1)
                   for i, item in enumerate(found["results"])}
    for uri, score in lexical.items():
        rank[uri] = rank.get(uri, 0.0) + score
        reasons.setdefault(uri, set()).add("matched local text")

    predicate = ontfs.graph.resolve_uri(summary_predicate)
    results = []
    for node, score in rank.items():
        if ontfs.graph.entity_status(node) == "superseded":
            continue
        label = next((str(value) for p in labels for value in graph.objects(node, p)), None)
        summary = next((str(value) for value in graph.objects(node, predicate)), None)
        results.append({
            "uri": str(node), "path": ontfs.graph.to_path(node), "label": label,
            "summary": summary, "why": sorted(reasons.get(node, ())), "score": score,
        })
    results.sort(key=lambda item: (-item["score"], item["uri"]))
    capped = []
    used_tokens = 0
    for item in results[:limit]:
        estimate = max(1, len(json.dumps(item, ensure_ascii=False)) // 4)
        if used_tokens + estimate > max_tokens:
            break
        capped.append(item)
        used_tokens += estimate
    return {
        "query": query, "results": capped,
        "stats": {"approx_tokens": used_tokens, "capped": len(capped) < len(results)},
    }
