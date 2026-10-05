"""Cross-process locking and crash-safe file replacement for ONTFS data."""

import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

_held_locks = threading.local()


@contextmanager
def locked(path):
    """Lock ``path`` via a sibling lock file for the duration of the context."""
    target = Path(str(path) + ".lock")
    target.parent.mkdir(parents=True, exist_ok=True)
    held = getattr(_held_locks, "paths", set())
    key = str(target.resolve())
    if key in held:
        yield
        return
    with target.open("a+b") as handle:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            unlock = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except ImportError:
            try:
                import msvcrt
                handle.seek(0)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                unlock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except ImportError as error:
                raise RuntimeError("ONTFS file locking is unsupported on this platform") from error
        held = set(held)
        held.add(key)
        _held_locks.paths = held
        try:
            yield
        finally:
            _held_locks.paths.remove(key)
            unlock()


def atomic_write(path, data):
    """Atomically replace a file after flushing its contents to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
