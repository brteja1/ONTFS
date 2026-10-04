"""Small deterministic embedding primitives with no runtime dependency."""

import hashlib
import math
import re


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
