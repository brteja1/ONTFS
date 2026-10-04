"""Small, dependency-free repository scanner for agent context."""

import ast
import subprocess
from pathlib import Path

from rdflib import Literal


IMPORTS = "custom:imports"
LANGUAGE = "custom:language"
GIT_COMMIT = "custom:gitCommit"
GIT_BRANCH = "custom:gitBranch"


def _git_info(directory):
    """Return stable Git context, or an empty mapping outside a repository."""
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=directory, check=True, capture_output=True, text=True,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=directory, check=True, capture_output=True, text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=directory, check=True, capture_output=True, text=True,
        ).stdout.strip() or "HEAD"
        return {"root": root, "commit": commit, "branch": branch}
    except (OSError, subprocess.CalledProcessError):
        return {}


def _imports(source):
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return sorted(names)


def scan(ontfs, path=".", include_git=True):
    """Index Python files and their imports into an existing ONTFS graph."""
    target = (ontfs.directory / path).resolve()
    if not target.exists():
        raise ValueError(f"scan path does not exist: {path}")
    if target.is_file():
        files = [target] if target.suffix == ".py" else []
        root = target.parent
    else:
        files = sorted(
            file for file in target.rglob("*.py")
            if ".git" not in file.parts and "__pycache__" not in file.parts
        )
        root = target

    git = _git_info(root) if include_git else {}
    scanned = 0
    skipped = 0
    import_count = 0

    def assert_fact(subject, predicate, obj, literal=False, source=None, note=None):
        s = ontfs.graph.resolve_uri(subject)
        p = ontfs.graph.resolve_uri(predicate)
        o = Literal(obj) if literal else ontfs.graph.resolve_uri(obj)
        ontfs.graph.graph.add((s, p, o))
        ontfs.graph.record_fact(
            s, p, o, source=source, asserted_by="ontfs-scanner", note=note,
        )

    for file in files:
        try:
            source = file.read_text(encoding="utf-8")
            imports = _imports(source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            skipped += 1
            continue
        try:
            relative = file.relative_to(ontfs.directory).as_posix()
        except ValueError:
            relative = str(file)
        assert_fact(relative, LANGUAGE, "python", literal=True, source=relative)
        for module in imports:
            assert_fact(
                relative, IMPORTS, f"urn:python:module:{module}",
                source=relative, note="Imported by Python source",
            )
        if git:
            assert_fact(relative, GIT_COMMIT, git["commit"], literal=True, source=relative)
            assert_fact(relative, GIT_BRANCH, git["branch"], literal=True, source=relative)
        scanned += 1
        import_count += len(imports)

    ontfs.graph.save()
    return {
        "path": str(target),
        "scanned": scanned,
        "skipped": skipped,
        "imports": import_count,
        "git": git,
    }
