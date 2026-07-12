"""Stable identities for cached calculation inputs."""
from __future__ import annotations

import os

from core.pdos_metadata import PDOSInputContext


def file_fingerprint(filepath: str) -> tuple[int, int]:
    """Return a cheap identity that changes when a VASP output is replaced.

    Nanosecond mtime avoids the former one-second collision window; file size
    catches common filesystem timestamp-resolution limitations.  A missing
    file receives an unverified sentinel and therefore cannot match a cache
    entry produced from a real file.
    """
    try:
        stat = os.stat(filepath)
    except OSError:
        return (0, 0)
    return (stat.st_mtime_ns, stat.st_size)


def context_fingerprint(context: PDOSInputContext) -> tuple:
    """Fingerprint every file the user explicitly authorized for one source."""
    return tuple(
        (path, file_fingerprint(path)) for path in context.authorized_paths)
