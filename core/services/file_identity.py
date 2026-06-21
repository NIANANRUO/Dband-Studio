"""Stable identities for cached calculation inputs."""
from __future__ import annotations

import os


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
