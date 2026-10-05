"""Small deterministic embedding primitives with no runtime dependency."""

import hashlib
import math
import re
import json
from pathlib import Path
from typing import List, Protocol

from ontfs.storage import atomic_write, locked


TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


def embed(text, dimensions=256):
    """Create a normalized hashing-trick vector for local semantic retrieval."""
    if dimensions <= 0:
        raise ValueError("embedding dimensions must be positive")
    vector = [0.0] * dimensions
    tokens = [token.casefold() for token in TOKEN_RE.findall(text)]
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def cosine(left, right):
    if len(left) != len(right):
        raise ValueError("embedding dimensions must match")
    return sum(a * b for a, b in zip(left, right))


class EmbeddingBackend(Protocol):
    name: str
    model: str
    dimensions: int

    def embed(self, texts: List[str]) -> List[List[float]]:
        ...


class HashedBackend:
    name = "hashed"
    model = "blake2-token-v1"

    def __init__(self, dimensions=256):
        if dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        self.dimensions = dimensions

    def embed(self, texts):
        return [embed(text, self.dimensions) for text in texts]


class SentenceTransformerBackend:
    name = "sentence-transformers"

    def __init__(self, model="all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "neural embeddings require the optional `ontfs[embed]` extra"
            ) from error
        self.model = model
        self._model = SentenceTransformer(model)
        self.dimensions = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts):
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in vectors]


def create_backend(name="hashed", dimensions=256, model=None):
    if name == "hashed":
        return HashedBackend(dimensions)
    if name == "sentence-transformers":
        return SentenceTransformerBackend(model or "all-MiniLM-L6-v2")
    raise ValueError(f"unknown embedding backend: {name}")


def _vector_key(backend, text):
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = f"{backend.name}\0{backend.model}\0{backend.dimensions}\0{content_hash}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def cached_embedding(ontfs, backend, text, source_path):
    cache_dir = ontfs.directory / ".ontfs.vectors"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _vector_key(backend, text)
    vector_file = cache_dir / (key + ".json")
    index_file = cache_dir / "files.json"
    with locked(index_file):
        if vector_file.exists():
            vector = json.loads(vector_file.read_text(encoding="utf-8"))
        else:
            vector = backend.embed([text])[0]
            atomic_write(vector_file, json.dumps(vector, separators=(",", ":")))
        index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else {}
        source_key = str(Path(source_path).resolve())
        previous = index.get(source_key)
        if previous and previous != key:
            try:
                (cache_dir / (previous + ".json")).unlink()
            except FileNotFoundError:
                pass
        index[source_key] = key
        atomic_write(index_file, json.dumps(index, indent=2) + "\n")
    return vector


def evict_files(ontfs, paths):
    cache_dir = ontfs.directory / ".ontfs.vectors"
    index_file = cache_dir / "files.json"
    if not index_file.exists():
        return 0
    removed = 0
    with locked(index_file):
        index = json.loads(index_file.read_text(encoding="utf-8"))
        for path in paths:
            key = index.pop(str(Path(path).resolve()), None)
            if key:
                try:
                    (cache_dir / (key + ".json")).unlink()
                    removed += 1
                except FileNotFoundError:
                    pass
        atomic_write(index_file, json.dumps(index, indent=2) + "\n")
    return removed
