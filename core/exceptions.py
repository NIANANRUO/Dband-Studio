"""
Custom exceptions for d-band center analyzer.

All exceptions inherit from DbandError so the UI layer can catch
them uniformly and display user-friendly messages.
"""

from typing import List, Optional


class DbandError(Exception):
    """Base exception for all d-band analyzer errors."""


class FileIntegrityError(DbandError):
    """The source is truncated, malformed, or internally inconsistent."""


class UnsupportedLayoutError(DbandError):
    """The projected-DOS column layout is not a supported VASP 5/6 layout."""

    def __init__(self, source: str, columns: int, detail: str = ""):
        message = f"{source}: unsupported projected DOS layout ({columns} data columns)."
        if detail:
            message += f" {detail}"
        super().__init__(message)


class AmbiguousLayoutError(DbandError):
    """The available metadata cannot uniquely determine a physical layout."""

    def __init__(self, source: str, columns: int, action: str):
        super().__init__(
            f"{source}: ambiguous projected DOS layout; {columns} columns have more than one valid "
            f"physical interpretation. {action}")


class StructureMismatchError(DbandError):
    """Structure and projected-DOS site counts cannot be aligned."""


class OrbitalUnavailableError(DbandError):
    """A requested orbital is not physically present in the source."""

    def __init__(self, orbital: str, available: tuple[str, ...]):
        choices = ", ".join(available) if available else "none"
        super().__init__(
            f"Requested orbital '{orbital}' is unavailable. Available VASP "
            f"projected orbitals: {choices}.")


class AtomSelectionError(DbandError):
    """An atom selection cannot be resolved for the available structure data."""


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
            "Supported formats: vasprun.xml, DOSCAR, and VASPKIT PDOS."
        )


class VASPKitAtomError(DbandError):
    """Element-based atom selection requires POSCAR for VASPKIT multi-atom PDOS."""

    def __init__(self, atoms_str: str, n_blocks: int):
        self.atoms_str = atoms_str
        self.n_blocks = n_blocks
        super().__init__(
            f"Atom selection '{atoms_str}' uses element names, but no structure "
            f"file was authorized. Use numeric indices (1–{n_blocks}) or "
            f"explicitly select a matching POSCAR/CONTCAR."
        )
