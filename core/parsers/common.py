"""Common utilities: helpers, file detection, and lazy pymatgen access.

CRITICAL: pymatgen is imported lazily to avoid adding 2-5s to application
startup.  Call _ensure_pymatgen() before any function that needs it.
"""

from __future__ import annotations

import os
import re
import logging
from typing import Dict, List, Optional
from collections import OrderedDict

import numpy as np

from core.exceptions import AtomNotFoundError
from core.parsers.constants import (
    s_orb_names, p_orb_names, d_orb_names, f_orb_names, all_orb_names,
)

_logger = logging.getLogger("dband.parsers")

# ---------- Lazy pymatgen (loaded on first use, not at import time) ----------

_pymatgen_loaded = False
_Vasprun = None
_Poscar = None
_Orbital = None
_Spin = None
_Doscar = None
_PYMATGEN_ORB_MAP: dict = {}
HAS_PYMATGEN = False


def _ensure_pymatgen():
    """Lazily import pymatgen and build orbital mapping.

    Called once at the start of parse_vasprun / parse_doscar.
    Subsequent calls return immediately.
    """
    global _pymatgen_loaded, HAS_PYMATGEN, _Vasprun, _Poscar, _Orbital, _Spin, _Doscar, _PYMATGEN_ORB_MAP

    if _pymatgen_loaded:
        return

    try:
        from pymatgen.io.vasp import Vasprun as _V, Poscar as _P
        from pymatgen.electronic_structure.core import Orbital as _O, Spin as _S
        try:
            from pymatgen.io.vasp import Doscar as _D
        except ImportError:
            _D = None

        _Vasprun, _Poscar, _Orbital, _Spin, _Doscar = _V, _P, _O, _S, _D
        HAS_PYMATGEN = True

        # Mutate _PYMATGEN_ORB_MAP in-place so imported references stay valid
        _PYMATGEN_ORB_MAP.clear()
        _PYMATGEN_ORB_MAP.update({
            _Orbital.s: "s",
            _Orbital.py: "py", _Orbital.pz: "pz", _Orbital.px: "px",
            _Orbital.dxy: "dxy", _Orbital.dyz: "dyz", _Orbital.dz2: "dz2",
            _Orbital.dxz: "dxz", _Orbital.dx2: "dx2-y2",
        })
        for attr, name in [("f_3", "f-3"), ("f_2", "f-2"), ("f_1", "f-1"),
                           ("f0", "f0"), ("f1", "f1"), ("f2", "f2"), ("f3", "f3")]:
            orb = getattr(_Orbital, attr, None)
            if orb is not None:
                _PYMATGEN_ORB_MAP[orb] = name

    except ImportError:
        HAS_PYMATGEN = False
        _Vasprun = _Poscar = _Orbital = _Spin = None
        _Doscar = None

    _pymatgen_loaded = True


# ---------- Helper functions ----------

def _ensure_positive(rho_dict: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """VASP/VASPKIT stores spin-down DOS as negative. abs() prevents cancellation."""
    return {k: np.abs(v) for k, v in rho_dict.items()}


def _site_symbol(site) -> str:
    """Extract the element symbol from a pymatgen Site.

    Handles both ``Structure`` sites (``site.specie.symbol``) and
    ``Composition``-bearing sites (``site.species.elements[0].symbol``),
    preferring ``species_string`` when available.  Centralised here to
    eliminate the repeated ternary expression that appeared in
    ``vasprun.py``, ``vaspkit.py`` and ``common.py``.
    """
    sym = getattr(site, "species_string", None)
    if sym is not None:
        return sym
    if hasattr(site, "specie"):
        return str(site.specie.symbol)
    return str(site.species.elements[0].symbol)


def _detect_has_spin(rho_dn: Dict[str, np.ndarray]) -> bool:
    """Return True iff any spin-down channel carries non-zero DOS.

    Used by both CalculationWorker and HybridizationWorker to decide
    whether a file is spin-polarised.  A channel that is all zeros on
    every orbital means the calculation was non-magnetic (or this atom
    has no spin splitting).
    """
    for arr in rho_dn.values():
        if np.any(arr != 0):
            return True
    return False


def _resolve_atom_indices(atoms_str: str, struct) -> list:
    """Parse atom selection string -> list of 0-based site indices."""
    target_sites = []
    if atoms_str.strip():
        parts = [p.strip() for p in atoms_str.split(",")]
        for p in parts:
            if re.match(r"^\d+$", p):
                idx = int(p) - 1
                if 0 <= idx < len(struct):
                    target_sites.append(idx)
            elif re.match(r"^\d+-\d+$", p):
                start, end = map(int, p.split("-"))
                # Clamp to struct size to avoid generating out-of-range
                # indices that would IndexError downstream.
                target_sites.extend(range(start - 1, min(end, len(struct))))
            else:
                for i, site in enumerate(struct):
                    if _site_symbol(site) == p:
                        target_sites.append(i)
    else:
        target_sites = list(range(len(struct)))

    target_sites = sorted(set(target_sites))
    if not target_sites:
        available = sorted(set(_site_symbol(s) for s in struct))
        raise AtomNotFoundError(atoms_str, available_species=available)
    return target_sites


# Simple cache for detect_file_type header reads (FIFO eviction to prevent OOM)
_MAX_DETECT_CACHE = 100
_detect_cache: OrderedDict = OrderedDict()


def detect_file_type(filepath: str) -> Optional[str]:
    """Auto-detect VASP output file type.

    Returns one of 'vasprun.xml', 'DOSCAR', 'VASPKIT PDOS', or None.
    """
    # Fast path: name-based detection (no I/O needed)
    bn = os.path.basename(filepath).upper()
    if "VASPRUN" in bn:
        return "vasprun.xml"
    if bn == "DOSCAR":
        return "DOSCAR"
    if "PDOS" in bn or "DOS_" in bn:
        return "VASPKIT PDOS"

    # Slow path: content-based XML detection (cached)
    if filepath in _detect_cache:
        _detect_cache.move_to_end(filepath)
        return _detect_cache[filepath]
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(500)
        result = "vasprun.xml" if ("<modeling>" in head or "<i name=" in head) else None
    except Exception:
        result = None
    if len(_detect_cache) >= _MAX_DETECT_CACHE:
        _detect_cache.popitem(last=False)
    _detect_cache[filepath] = result
    return result


def get_pymatgen_classes() -> dict:
    """Return pymatgen classes after lazy loading.

    Provides public access to Vasprun, Poscar, Orbital, Spin, Doscar.
    Raises ImportError if pymatgen is not available.
    """
    _ensure_pymatgen()
    if not HAS_PYMATGEN:
        raise ImportError("pymatgen is required for this operation")
    return {
        "Vasprun": _Vasprun,
        "Poscar": _Poscar,
        "Orbital": _Orbital,
        "Spin": _Spin,
        "Doscar": _Doscar,
    }


def _load_structure_near(filepath: str):
    """Try to load a pymatgen Structure from POSCAR/CONTCAR near *filepath*."""
    _ensure_pymatgen()
    if not HAS_PYMATGEN:
        return None
    for name in ("POSCAR", "CONTCAR"):
        candidate = os.path.join(os.path.dirname(filepath), name)
        if os.path.exists(candidate):
            try:
                return _Poscar.from_file(candidate).structure
            except Exception:
                pass
    return None
