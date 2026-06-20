"""
Miscellaneous helper functions.
"""
from __future__ import annotations

import os


def get_app_version() -> str:
    """Return the application version from a single source of truth.

    Resolution order:
        1. ``importlib.metadata`` if the package is installed.
        2. ``pyproject.toml`` ``[project].version`` field (dev mode).
        3. Hard-coded fallback ``"1.0.0"``.

    All display surfaces (splash, about dialog, main window title) MUST
    call this function instead of hard-coding a version string.
    """
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            return version("dband-studio")
        except PackageNotFoundError:
            pass
    except ImportError:
        pass

    # Dev mode: parse pyproject.toml directly (no third-party dep required).
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        toml_path = os.path.join(root, "pyproject.toml")
        if os.path.exists(toml_path):
            with open(toml_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("version") and "=" in line:
                        # version = "1.0.0"
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass

    return "1.0.0"


def format_orbital_display(oname: str) -> str:
    """Convert internal orbital name to display-friendly string (e.g. dz2 -> dz²)."""
    return oname.replace("dz2", "dz\u00b2").replace("dx2-y2", "dx\u00b2-y\u00b2")


def get_y_limits_for_x_range(x_arr, y_arrs, x_min, x_max):
    """
    Pure function to compute min/max Y values for multiple Y arrays
    within a specific X range. Returns (y_min, y_max) or (inf, -inf).
    """
    import numpy as np
    y_min_visible = float('inf')
    y_max_visible = float('-inf')
    
    if x_arr is None or len(x_arr) == 0:
        return y_min_visible, y_max_visible
        
    mask = (x_arr >= x_min) & (x_arr <= x_max)
    if not np.any(mask):
        return y_min_visible, y_max_visible
        
    for y_arr in y_arrs:
        if y_arr is None or len(y_arr) != len(x_arr):
            continue
        valid_y = y_arr[mask]
        if len(valid_y) > 0:
            y_min_visible = min(y_min_visible, np.min(valid_y))
            y_max_visible = max(y_max_visible, np.max(valid_y))
            
    return y_min_visible, y_max_visible
