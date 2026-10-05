"""Dependency-free polling watcher for incremental repository scans."""

import time
from pathlib import Path

from ontfs.embeddings import evict_files
from ontfs.search import TEXT_EXTENSIONS


def snapshot(path):
    root = Path(path).resolve()
    if root.is_file():
        files = [root] if root.suffix.casefold() in TEXT_EXTENSIONS else []
    else:
        files = sorted(
            file for file in root.rglob("*")
            if file.is_file() and file.suffix.casefold() in TEXT_EXTENSIONS
            and ".git" not in file.parts and "__pycache__" not in file.parts
            and ".ontfs.vectors" not in file.parts
        )
    return {
        str(file): (file.stat().st_mtime_ns, file.stat().st_size)
        for file in files
    }


def watch(ontfs, path=".", interval=1.0, iterations=None, include_git=True):
    """Scan initially, then rescan after detected supported text-file changes.

    ``iterations`` is the number of polling cycles. ``None`` watches forever;
    zero performs the initial scan and returns. Changed/removed files have
    their persistent embedding cache entries evicted.
    """
    target = (ontfs.directory / path).resolve()
    if not target.exists():
        raise ValueError(f"watch path does not exist: {path}")
    if interval < 0:
        raise ValueError("interval must be non-negative")
    if iterations is not None and iterations < 0:
        raise ValueError("iterations must be non-negative")

    results = [ontfs.scan(path=path, include_git=include_git)]
    previous = snapshot(target)
    cycle = 0
    while iterations is None or cycle < iterations:
        if interval:
            time.sleep(interval)
        current = snapshot(target)
        if current != previous:
            changed = [name for name in set(previous) | set(current)
                       if previous.get(name) != current.get(name)]
            evict_files(ontfs, changed)
            results.append(ontfs.scan(path=path, include_git=include_git))
            previous = current
        cycle += 1
    return results
