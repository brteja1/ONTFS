"""Bounded lexical search augmented with ONTFS graph context."""

import re
from pathlib import Path
from ontfs.embeddings import cached_embedding, cosine, create_backend


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


def search(ontfs, query, path=".", limit=20, related_to=None, depth=1,
           vector=False, embedding_dimensions=256, embedding_backend="hashed",
           embedding_model=None):
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
    backend = create_backend(embedding_backend, embedding_dimensions, embedding_model) if vector else None
    query_vector = backend.embed([query])[0] if vector else None
    related_uris = set()
    if related_to is not None:
        context = ontfs.context(related_to, depth=depth, limit=500)
        related_uris.add(str(ontfs.graph.resolve_uri(context["entity"])))
        for fact in context["facts"]:
            for term in (fact["subject"], fact["object"]):
                related_uris.add(str(ontfs.graph.resolve_uri(term)))

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
        vector_score = 0.0
        if vector:
            vector_score = cosine(query_vector, cached_embedding(ontfs, backend, text, file))
        if not hits and not vector:
            continue
        uri = str(ontfs.graph.resolve_uri(str(file)))
        graph_boost = 5 if uri in related_uris else 0
        name_boost = sum(2 for token in query_tokens if token in file.name.casefold())
        score = hits + graph_boost + name_boost + (vector_score * 10.0)
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
            "vector_score": round(vector_score, 6),
            "snippet": snippet[:240],
        })

    results.sort(key=lambda item: (-item["score"], item["path"]))
    return {
        "query": query,
        "related_to": related_to,
        "vector": vector,
        "embedding_backend": backend.name if backend else None,
        "embedding_model": backend.model if backend else None,
        "embedding_dimensions": backend.dimensions if backend else None,
        "results": results[:limit],
    }
