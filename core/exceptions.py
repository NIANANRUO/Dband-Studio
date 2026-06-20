"""
Custom exceptions for d-band center analyzer.

All exceptions inherit from DbandError so the UI layer can catch
them uniformly and display user-friendly messages.
"""

from typing import List, Optional


class DbandError(Exception):
    """Base exception for all d-band analyzer errors."""


class AtomNotFoundError(DbandError):
    """No matching atoms found in the structure for the given selection."""

    def __init__(self, atoms_str: str, available_species: Optional[List[str]] = None):
        self.atoms_str = atoms_str
        self.available_species = available_species or []
        hint = f"No atoms matching '{atoms_str}' found in the structure."
        if self.available_species:
            hint += f" Available elements: {', '.join(self.available_species)}."
        super().__init__(hint)


class OrbitalMissingError(DbandError):
    """Expected orbitals (e.g. d-orbitals) are absent from the PDOS data."""

    def __init__(self, filepath: str, skipped_types: List[str], hint: str = ""):
        self.filepath = filepath
        self.skipped_types = skipped_types
        msg = (
            f"Orbital data missing in '{filepath}'. "
            f"Skipped types: {sorted(skipped_types)}. "
        )
        if hint:
            msg += hint
        else:
            msg += "Check LORBIT setting in VASP calculation (need LORBIT >= 10 for d-orbital projection)."
        super().__init__(msg)


class MissingProjectedDOSError(DbandError):
    """PDOS data is absent or all-zero for the selected atoms."""

    def __init__(self, label: str, filepath: str = ""):
        self.label = label
        self.filepath = filepath
        msg = (
            f"'{label}': selected atoms have NO projected DOS (all zero). "
            "Check LORBIT setting in VASP calculation (need LORBIT >= 10)."
        )
        super().__init__(msg)


class FileTypeError(DbandError):
    """Cannot detect or unsupported file type."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        super().__init__(
            f"Cannot detect file type for '{filepath}'. "
            "Supported formats: vasprun.xml, DOSCAR (with POSCAR/CONTCAR), VASPKIT PDOS."
        )


class VASPKitAtomError(DbandError):
    """Element-based atom selection requires POSCAR for VASPKIT multi-atom PDOS."""

    def __init__(self, atoms_str: str, n_blocks: int):
        self.atoms_str = atoms_str
        self.n_blocks = n_blocks
        super().__init__(
            f"Atom selection '{atoms_str}' uses element names, but no POSCAR/CONTCAR found "
            f"alongside the VASPKIT PDOS file. Use numeric indices (1–{n_blocks}) instead, "
            f"or place POSCAR in the same directory."
        )
