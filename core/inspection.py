"""Lightweight, calculation-free inspection of projected-DOS sources."""

from __future__ import annotations

import os
import re
from typing import Optional

from core.exceptions import FileIntegrityError
from core.pdos_metadata import PDOSCapabilities, PDOSInputContext
from core.parsers.constants import all_orb_names


def inspect_doscar(context: PDOSInputContext) -> PDOSCapabilities:
    filepath = context.primary_path
    from core.parsers.common import _load_structure_file
    from core.parsers.doscar import (
        _classify_pdos_layout,
        _metadata_noncollinear_hint,
        _read_doscar_raw,
    )

    _energy, _total, per_atom, _ef, is_spin = _read_doscar_raw(filepath)
    if not per_atom:
        raise FileIntegrityError(
            f"{filepath}: DOSCAR contains no site-projected DOS blocks. "
            "Set LORBIT=10 or LORBIT=11 and rerun VASP.")
    width = per_atom[0].shape[1]
    if any(block.shape[1] != width for block in per_atom):
        raise FileIntegrityError(
            f"{filepath}: DOSCAR ion blocks use inconsistent column counts.")
    layout = _classify_pdos_layout(
        width, total_is_spin=is_spin,
        noncollinear_hint=_metadata_noncollinear_hint(
            filepath, metadata_path=context.metadata_path))
    structure = None
    if context.structure_path:
        try:
            structure = _load_structure_file(context.structure_path)
        except Exception as exc:
            raise FileIntegrityError(
                f"Cannot read explicitly selected structure "
                f"'{context.structure_path}': {exc}") from exc
    if structure is not None and len(structure) != len(per_atom):
        raise FileIntegrityError(
            f"{filepath}: explicitly selected structure "
            f"'{context.structure_path}' has {len(structure)} sites but DOSCAR has "
            f"{len(per_atom)} projected-DOS blocks.")
    warnings = () if structure is not None else (
        "No structure file was authorized; use numeric indices or select one explicitly.",)
    return PDOSCapabilities(
        source_format="DOSCAR",
        vasp_version=None,
        spin_mode=layout.mode,
        orbital_resolution=layout.orbital_resolution,
        available_orbitals=layout.orbitals,
        structure_available=structure is not None,
        atom_selection_modes=("index", "element") if structure is not None else ("index",),
        field_source="doscar_layout",
        warnings=warnings,
    )


def inspect_vaspkit(context: PDOSInputContext) -> PDOSCapabilities:
    filepath = context.primary_path
    fields: list[str] = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if not line.lstrip().startswith("#"):
                continue
            tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", line)
            mapped = [token.lower() for token in tokens]
            fields = [name for name in mapped if name in all_orb_names]
            if fields:
                break
    if not fields:
        raise FileIntegrityError(
            f"{filepath}: VASPKIT PDOS header does not declare recognizable orbitals.")
    structure = bool(context.structure_path)
    warnings = (
        "VASPKIT PDOS does not embed a Fermi level; verify that energies are already aligned.",)
    if not structure:
        warnings += ("No matching structure file; use numeric atom indices.",)
    resolution = "lm" if any(name not in {"s", "p", "d", "f"} for name in fields) else "l"
    return PDOSCapabilities(
        source_format="VASPKIT PDOS", vasp_version=None,
        spin_mode="unknown", orbital_resolution=resolution,
        available_orbitals=tuple(dict.fromkeys(fields)),
        structure_available=structure,
        atom_selection_modes=("index", "element") if structure else ("index",),
        field_source="plugin", warnings=warnings)


def inspect_source(context: PDOSInputContext) -> PDOSCapabilities:
    if context.source_format == "DOSCAR":
        return inspect_doscar(context)
    if context.source_format == "VASPKIT PDOS":
        return inspect_vaspkit(context)
    if context.source_format == "vasprun.xml":
        from core.parsers.vasprun import inspect_vasprun
        return inspect_vasprun(context.primary_path, input_context=context)
    raise FileIntegrityError(
        f"No inspector is registered for {context.source_format!r}.")
