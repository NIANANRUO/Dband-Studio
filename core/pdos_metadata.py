"""Immutable provenance describing the physical interpretation of PDOS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple


@dataclass(frozen=True)
class PDOSInputContext:
    """User-authorized files that may be read for one PDOS source."""

    primary_path: str
    source_format: str
    structure_path: Optional[str] = None
    metadata_path: Optional[str] = None
    spin_partner_path: Optional[str] = None

    @property
    def authorized_paths(self) -> Tuple[str, ...]:
        return tuple(path for path in (
            self.primary_path, self.structure_path,
            self.metadata_path, self.spin_partner_path,
        ) if path)


def input_context_from_entry(
    entry: dict, source_format: str,
) -> PDOSInputContext:
    """Build an input context solely from paths explicitly stored in an entry."""
    auxiliary = entry.get("auxiliary_files") or {}
    return PDOSInputContext(
        primary_path=entry["path"],
        source_format=source_format,
        structure_path=auxiliary.get("structure"),
        metadata_path=auxiliary.get("metadata"),
        spin_partner_path=auxiliary.get("spin_partner"),
    )


@dataclass(frozen=True)
class PDOSCapabilities:
    """Validated capabilities exposed by one projected-DOS source.

    Principal quantum numbers are intentionally absent: ordinary VASP PDOS
    files expose angular-momentum projections, not independent 3d/4d/5d data.
    """

    source_format: str
    vasp_version: Optional[str]
    spin_mode: Literal["nonspin", "collinear", "noncollinear", "unknown"]
    orbital_resolution: Literal["lm", "l", "unknown"]
    available_orbitals: Tuple[str, ...]
    structure_available: bool
    atom_selection_modes: Tuple[str, ...]
    field_source: Literal["declared", "known_layout", "doscar_layout", "plugin"]
    warnings: Tuple[str, ...] = ()

    def supports_orbital(self, orbital: str) -> bool:
        return orbital in self.available_orbitals

    @property
    def can_select_elements(self) -> bool:
        return "element" in self.atom_selection_modes


@dataclass(frozen=True)
class PDOSMetadata:
    """Facts required to prevent a PDOS channel from being mislabelled.

    ``mode='noncollinear'`` means the exposed up/down arrays are projections
    reconstructed along VASP's sigma-3/SAXIS direction, not collinear spin
    channels.  The tuple interface intentionally remains separate so existing
    plugins and UI callers retain backward compatibility.
    """

    mode: Literal["nonspin", "collinear", "noncollinear", "unknown"]
    orbital_resolution: Literal["lm", "l", "unknown"]
    spin_axis: Optional[Tuple[float, float, float]]
    source_format: str
    capabilities: Optional[PDOSCapabilities] = None

    @property
    def spin_channel_label(self) -> str:
        if self.mode == "noncollinear":
            return "SAXIS-projected spin"
        if self.mode == "collinear":
            return "collinear spin"
        return "total DOS"
