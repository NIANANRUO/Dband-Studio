"""
Unified DataLoader — single entry point for all VASP file types.

Uses a registry/strategy pattern for parser dispatch (OCP-compliant).
New formats can be registered via DataLoader.register_parser().

Usage:
    from core.loader import DataLoader
    energy, rho_up, rho_dn, rho_total, ef = DataLoader.load_spin_all(fp, atoms)
    energy, rho, ef = DataLoader.load(fp, atoms, spin="total")

CRITICAL:  Heavy parser modules (pymatgen) are loaded lazily via
_ensure_parsers() — only called when parse/load methods are invoked,
not at import time.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from core import parsers
from core.exceptions import FileTypeError, MissingProjectedDOSError


def _ensure_parsers():
    """Lazily load heavy parser modules on first use."""
    parsers._load_submodules()


def _vaspkit_adapter(filepath, atoms, spin, orbitals=None):
    """Adapter to unify VASPKIT parser signature with vasprun/doscar."""
    return parsers.parse_vaspkit(filepath, spin, atoms_str=atoms, orbitals=orbitals)


class DataLoader:
    """Unified interface for loading PDOS data from any supported VASP format.

    Parser dispatch uses a registry pattern — new formats can be added
    via register_parser() without modifying this class (OCP-compliant).
    """

    # Registry: file_type -> parser callable(filepath, atoms, spin, orbitals)
    _parsers: Dict[str, Callable] = {}

    @classmethod
    def register_parser(cls, ftype: str, parser_func: Callable) -> None:
        """Register a parser for a file type (extension point for plugins)."""
        cls._parsers[ftype] = parser_func

    @staticmethod
    def detect(filepath: str) -> str:
        """Detect file type.

        Raises FileTypeError if detection fails.
        """
        _ensure_parsers()
        ftype = parsers.detect_file_type(filepath)
        if ftype is None:
            raise FileTypeError(filepath)
        return ftype

    @classmethod
    def load(
        cls,
        filepath: str,
        atoms: str,
        spin: str = "total",
        orbitals: Optional[List[str]] = None,
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray], float]:
        """Load PDOS for a single spin channel.

        Returns: (energy, rho_dict, ef)
        """
        _ensure_parsers()
        ftype = cls.detect(filepath)
        parser = cls._parsers.get(ftype)
        if parser is None:
            raise FileTypeError(filepath)
        return parser(filepath, atoms, spin, orbitals=orbitals)

    @classmethod
    def load_spin_all(
        cls,
        filepath: str,
        atoms: str,
        orbitals: Optional[List[str]] = None,
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, np.ndarray], float]:
        """Load PDOS for all spin channels at once (single XML/DOSCAR parse).

        Returns: (energy, rho_up, rho_dn, rho_total, ef)
        """
        _ensure_parsers()
        ftype = cls.detect(filepath)

        if ftype == "vasprun.xml":
            return parsers.parse_vasprun_spin_all(filepath, atoms, orbitals=orbitals)
        elif ftype == "DOSCAR":
            return parsers.parse_doscar_spin_all(filepath, atoms, orbitals=orbitals)
        elif ftype == "VASPKIT PDOS":
            return parsers.parse_vaspkit_spin_all(filepath, atoms, orbitals=orbitals)
        # Unknown type — fall back to double load (keeps backward compat for plugins).
        energy, rho_up, ef = cls.load(filepath, atoms, spin="up", orbitals=orbitals)
        _, rho_dn, _ = cls.load(filepath, atoms, spin="down", orbitals=orbitals)
        # Magnetic systems: total DOS must be |ρ_up| + |ρ_dw| (weighted
        # synthesis per the Hammer–Nørskov d-band formula), NOT a simple
        # sum which would cancel signed spin-down contributions.
        rho_total = {o: np.abs(rho_up.get(o, np.zeros_like(energy)))
                     + np.abs(rho_dn.get(o, np.zeros_like(energy)))
                     for o in (orbitals or parsers.all_orb_names)}
        return energy, rho_up, rho_dn, rho_total, ef


# Register built-in parsers
DataLoader.register_parser("vasprun.xml", parsers.parse_vasprun)
DataLoader.register_parser("DOSCAR", parsers.parse_doscar)
DataLoader.register_parser("VASPKIT PDOS", _vaspkit_adapter)
