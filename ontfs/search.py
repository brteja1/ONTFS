"""Bounded lexical search augmented with ONTFS graph context."""

import re
from pathlib import Path


TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".h", ".hpp", ".java", ".js", ".json",
    ".md", ".py", ".rst", ".toml", ".txt", ".yaml", ".yml",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


def _tokens(text):
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def _files(root):
    if root.is_file():
        return [root] if root.suffix.casefold() in TEXT_EXTENSIONS else []
    return sorted(
        file for file in root.rglob("*")
        if file.is_file()
        and file.suffix.casefold() in TEXT_EXTENSIONS
        and ".git" not in file.parts
        and "__pycache__" not in file.parts
        and file.name not in {".ontfs.ttl", ".ontfs.proposals.json"}
    )


def search(ontfs, query, path=".", limit=20, related_to=None, depth=1):
    """Search local text and boost files connected to a graph entity."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if limit <= 0:
        raise ValueError("limit must be positive")
    if depth < 0:
        raise ValueError("depth must be non-negative")

    root = (ontfs.directory / path).resolve()
    if not root.exists():
        raise ValueError(f"search path does not exist: {path}")
    query_tokens = _tokens(query)
    related_uris = set()
    if related_to is not None:
        context = ontfs.context(related_to, depth=depth, limit=500)
        related_uris.add(context["entity"])
        for fact in context["facts"]:
            related_uris.update((fact["subject"], fact["object"]))

    results = []
    for file in _files(root):
        try:
            if file.stat().st_size > 1_000_000:
                continue
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        tokens = _tokens(text)
        counts = {token: tokens.count(token) for token in query_tokens}
        hits = sum(counts.values())
        if not hits:
            continue
        uri = file.resolve().as_uri()
        graph_boost = 5 if uri in related_uris else 0
        name_boost = sum(2 for token in query_tokens if token in file.name.casefold())
        score = hits + graph_boost + name_boost
        lines = text.splitlines()
        snippet = next((line.strip() for line in lines if any(
            token in line.casefold() for token in query_tokens
        )), "")
        results.append({
            "path": str(file),
            "uri": uri,
            "score": score,
            "text_hits": hits,
            "graph_boost": graph_boost,
            "snippet": snippet[:240],
        })

    results.sort(key=lambda item: (-item["score"], item["path"]))
    return {"query": query, "related_to": related_to, "results": results[:limit]}
