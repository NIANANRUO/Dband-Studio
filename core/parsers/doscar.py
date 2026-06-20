"""DOSCAR parser — standalone (no pymatgen ``Doscar`` dependency).

Recent pymatgen releases (2024+) removed the ``Doscar`` class entirely, so the
old pymatgen-based path is dead on modern installs.  This module parses the
raw DOSCAR byte layout directly, supporting both non-spin-polarised and
spin-polarised outputs and ``LORBIT`` 10/11 projected DOS.

DOSCAR layout
-------------
Line 0–4 : 5 header lines (system info, lattice, comment).
Line 5    : ``EMAX EMIN NEDOS EFERMI weight`` (space-separated).
Line 6 .. 6+NEDOS-1           : total DOS (NEDOS rows).
            non-spin : energy, total, integrated            (3 cols)
            spin     : energy, up, down, int-up, int-down   (5 cols)
Then, per ion (in POSCAR/CONTCAR site order — guaranteed by VASP):
            1 header line + NEDOS data rows.
            LORBIT=11, 9 orbs : energy, 9×(up[,down])        (10 or 19 cols)
            LORBIT=10, 4 orbs : energy, 4×(up[,down])        ( s p d f )

Spin sign convention
--------------------
VASP writes spin-down DOS as **negative** values in the total DOS block
(columns: energy, up, down, int-up, int-down).  However, in the per-atom
projected DOS block, VASP uses an **interleaved layout** with **positive**
values for both channels:

    energy, s_up, s_dn, py_up, py_dn, pz_up, pz_dn, px_up, px_dn, ...

This is NOT a block layout (s_up, py_up, ..., s_dn, py_dn, ...).
``_select_orbital_columns`` maps orbital *i* to columns ``2*i`` (up) and
``2*i+1`` (down) for spin-polarised data.  ``_accumulate`` returns the raw
signed values; ``parse_doscar_spin_all`` applies ``abs()`` once at the
boundary — the single source of truth for the magnitude convention.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.exceptions import DbandError
from core.parsers.common import (
    _load_structure_near,
    _resolve_atom_indices,
)
from core.parsers.constants import (
    s_orb_names, p_orb_names, d_orb_names, f_orb_names, all_orb_names,
)

_logger = logging.getLogger("dband.parsers")

# Orbital name order VASP writes for each LORBIT scheme (per spin channel).
# LORBIT=11 (lm-decomposed): s + 3p + 5d + 7f  = 16 columns per channel.
_LORBIT11_ORBS = s_orb_names + p_orb_names + d_orb_names + f_orb_names
# LORBIT=10 (l-decomposed): s, p, d, f = 4 columns per channel.
_LORBIT10_ORBS = ["s", "p", "d", "f"]


@dataclass(frozen=True)
class PDOSLayout:
    """Physical interpretation of one DOSCAR site-projected data row."""

    mode: str
    orbital_resolution: str
    orbitals: Tuple[str, ...]
    components: Tuple[str, ...]


def _classify_pdos_layout(n_cols: int, *, total_is_spin: bool) -> PDOSLayout:
    """Classify VASP projected DOS columns without heuristic truncation.

    ``n_cols`` excludes the leading energy column.  VASP emits one component
    for non-spin data, interleaved up/down pairs for collinear data, and four
    components (total, m1, m2, m3) for noncollinear data.
    """
    lm_counts = {1, 5, 9, len(_LORBIT11_ORBS)}
    l_counts = {len(_LORBIT10_ORBS)}

    if total_is_spin:
        if n_cols % 2:
            raise DbandError(
                f"unsupported projected DOS layout: {n_cols} columns is not "
                "an interleaved collinear pair layout.")
        count = n_cols // 2
        if count in lm_counts:
            return PDOSLayout("collinear", "lm", tuple(_LORBIT11_ORBS[:count]),
                              ("up", "down"))
        if count in l_counts:
            return PDOSLayout("collinear", "l", tuple(_LORBIT10_ORBS),
                              ("up", "down"))
    else:
        if n_cols in lm_counts:
            return PDOSLayout("nonspin", "lm", tuple(_LORBIT11_ORBS[:n_cols]),
                              ("total",))
        if n_cols in l_counts:
            return PDOSLayout("nonspin", "l", tuple(_LORBIT10_ORBS),
                              ("total",))
        if n_cols % 4 == 0:
            count = n_cols // 4
            if count in lm_counts:
                return PDOSLayout("noncollinear", "lm",
                                  tuple(_LORBIT11_ORBS[:count]),
                                  ("total", "m1", "m2", "m3"))
            if count in l_counts:
                return PDOSLayout("noncollinear", "l", tuple(_LORBIT10_ORBS),
                                  ("total", "m1", "m2", "m3"))

    raise DbandError(
        f"unsupported projected DOS layout: {n_cols} columns; refusing to "
        "guess orbital or spin-column mapping.")


def _project_noncollinear_spin(
    total: np.ndarray, m3: np.ndarray, *, tolerance: float = 1e-8,
) -> Tuple[np.ndarray, np.ndarray]:
    """Project noncollinear DOS onto VASP's sigma-3 (SAXIS) direction."""
    total = np.asarray(total, dtype=np.float64)
    m3 = np.asarray(m3, dtype=np.float64)
    if total.shape != m3.shape or not np.isfinite(total).all() or not np.isfinite(m3).all():
        raise DbandError("Noncollinear total DOS and m3 must be finite, matching arrays.")
    if np.any(total < -tolerance) or np.any(np.abs(m3) > total + tolerance):
        raise DbandError("Noncollinear magnetization density exceeds total DOS.")
    total = np.maximum(total, 0.0)
    return (total + m3) * 0.5, (total - m3) * 0.5


def _accumulate_noncollinear(
    per_atom: List[np.ndarray], target_indices: List[int], target_orbs: List[str],
) -> Dict[str, Dict[str, np.ndarray]]:
    """Sum total/m1/m2/m3 PDOS over selected atoms before spin projection."""
    if not per_atom:
        raise DbandError("No site-projected DOS blocks available.")
    n_energy = per_atom[0].shape[0]
    result = {
        component: {orb: np.zeros(n_energy, dtype=np.float64) for orb in target_orbs}
        for component in ("total", "m1", "m2", "m3")
    }
    for idx in target_indices:
        if not 0 <= idx < len(per_atom):
            raise DbandError(f"Selected atom index {idx + 1} is outside DOSCAR PDOS blocks.")
        arr = per_atom[idx]
        if arr.shape[0] != n_energy:
            raise DbandError("DOSCAR atom PDOS blocks have inconsistent energy lengths.")
        layout = _classify_pdos_layout(arr.shape[1], total_is_spin=False)
        if layout.mode != "noncollinear":
            raise DbandError("Expected noncollinear total/m1/m2/m3 projected DOS layout.")
        for orb in target_orbs:
            if orb not in layout.orbitals:
                continue
            column = layout.orbitals.index(orb) * 4
            for offset, component in enumerate(layout.components):
                result[component][orb] += arr[:, column + offset]
    return result


def _read_doscar_raw(filepath: str):
    """Parse a DOSCAR into (energy, total_dos, per_atom_dos, efermi, is_spin).

    ``total_dos``    : ndarray (NEDOS,) or (NEDOS, 2) for spin.
    ``per_atom_dos`` : list of ndarrays, one per ion; shape (NEDOS, n_orb_cols)
                       where ``n_orb_cols`` excludes the leading energy column.
    """
    with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
        lines = fh.readlines()

    if len(lines) < 7:
        raise DbandError(f"{filepath}: DOSCAR too short ({len(lines)} lines).")

    header = lines[5].split()
    if len(header) < 5:
        raise DbandError(
            f"{filepath}: malformed DOSCAR header line 6: {lines[5]!r}")
    try:
        nedos = int(float(header[2]))
        efermi = float(header[3])
    except (ValueError, IndexError):
        raise DbandError(
            f"{filepath}: cannot read NEDOS/EFERMI from header: {lines[5]!r}")

    # Total DOS block.
    total_start = 6
    total_block = lines[total_start:total_start + nedos]
    if len(total_block) < nedos:
        raise DbandError(
            f"{filepath}: total DOS truncated (have {len(total_block)}, "
            f"expected {nedos}).")

    total_arr = _parse_float_block(
        total_block, expected_rows=nedos, context="total DOS")
    energy = total_arr[:, 0]
    # Spin detection from total-DOS column count: 5 cols => spin-polarised.
    is_spin = total_arr.shape[1] >= 4

    # Per-ion projected DOS. Each ion occupies (1 header + nedos data) lines.
    per_atom: List[np.ndarray] = []
    cursor = total_start + nedos
    n_lines = len(lines)
    while cursor + nedos < n_lines + 1:
        # Header line (same layout as the top one). Skip; we don't need it.
        cursor += 1
        if cursor + nedos > n_lines:
            break
        block = lines[cursor:cursor + nedos]
        arr = _parse_float_block(
            block, expected_rows=nedos, context=f"ion {len(per_atom) + 1} PDOS")
        per_atom.append(arr[:, 1:])  # drop energy column
        cursor += nedos

    return energy, total_arr[:, 1:], per_atom, efermi, is_spin


def _parse_float_block(
    block: List[str],
    expected_rows: Optional[int] = None,
    context: str = "DOSCAR block",
) -> np.ndarray:
    """Parse a list of whitespace-separated numeric lines into a 2-D array.

    All rows must share the same column count; rows that fail to parse are
    skipped (defensive against trailing blank lines).
    """
    rows: List[List[float]] = []
    width = 0
    for ln in block:
        parts = ln.split()
        if not parts:
            continue
        try:
            row = [float(p) for p in parts]
        except ValueError as exc:
            raise DbandError(
                f"Invalid numeric value in {context}: {ln!r}") from exc
        if width == 0:
            width = len(row)
        elif len(row) != width:
            # Ragged row — stop to avoid silently misaligning columns.
            raise DbandError(
                f"Ragged {context}: expected {width} columns, "
                f"got {len(row)} in row {len(rows) + 1}.")
        rows.append(row)
    if not rows:
        raise DbandError(f"No numeric data found in {context}.")
    if expected_rows is not None and len(rows) != expected_rows:
        raise DbandError(
            f"Truncated {context}: parsed {len(rows)} rows, "
            f"expected {expected_rows}.")
    return np.asarray(rows, dtype=np.float64)


def _select_orbital_columns(
    n_cols: int,
    is_spin: bool,
    target_orbs: List[str],
) -> Dict[str, Tuple[int, ...]]:
    """Map target orbital names to data column indices (per spin channel).

    Returns ``{orb_name: (up_col, dn_col)}`` where columns index into the
    per-atom data array (energy column already stripped).  ``dn_col`` is
    ``None`` for non-spin DOS.  Orbitals absent from the file are omitted.

    VASP DOSCAR per-atom spin-polarised layout is **interleaved**:
        energy, s_up, s_dn, py_up, py_dn, pz_up, pz_dn, ...
    NOT block layout (s_up, py_up, ..., s_dn, py_dn, ...).
    For spin-polarised data, orbital *i* occupies columns ``2*i`` (up) and
    ``2*i+1`` (down).  For non-spin, orbital *i* occupies column ``i``.
    """
    per_channel = n_cols // (2 if is_spin else 1)
    if per_channel in (len(_LORBIT11_ORBS), 9, 5, 1):
        # 16 (full l+m), 9 (s+p+d), 5 (s+p+d trim), or single column.
        order = _LORBIT11_ORBS[:per_channel] if per_channel <= 16 else _LORBIT11_ORBS
    elif per_channel == len(_LORBIT10_ORBS):
        order = _LORBIT10_ORBS
    else:
        # Unknown column count: fall back to LORBIT=11 names, truncated/padded.
        order = _LORBIT11_ORBS[:per_channel]

    mapping: Dict[str, Tuple[int, ...]] = {}
    for orb in target_orbs:
        if orb not in order:
            continue
        ci = order.index(orb)
        if is_spin:
            # Interleaved: up=2*ci, dn=2*ci+1
            mapping[orb] = (ci * 2, ci * 2 + 1)
        else:
            mapping[orb] = (ci,)
    return mapping


def _accumulate(
    per_atom: List[np.ndarray],
    is_spin: bool,
    target_indices: List[int],
    target_orbs: List[str],
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """Sum projected DOS over selected atoms for up/down channels."""
    up = {o: None for o in target_orbs}
    dn = {o: None for o in target_orbs}

    for idx in target_indices:
        if idx >= len(per_atom):
            _logger.warning(
                "DOSCAR: atom index %d exceeds available ions (%d), skipping.",
                idx, len(per_atom))
            continue
        arr = per_atom[idx]
        col_map = _select_orbital_columns(arr.shape[1], is_spin, target_orbs)
        for orb, cols in col_map.items():
            if is_spin:
                up_val = arr[:, cols[0]]
                dn_val = arr[:, cols[1]]
            else:
                up_val = arr[:, cols[0]]
                dn_val = None
            up[orb] = up_val if up[orb] is None else up[orb] + up_val
            if dn_val is not None:
                dn[orb] = dn_val if dn[orb] is None else dn[orb] + dn_val

    # Materialise missing orbitals as zero arrays sized to the first present one.
    ref = next((v for v in up.values() if v is not None), None)
    if ref is None:
        # No orbital data at all — size from per_atom if present.
        n = per_atom[0].shape[0] if per_atom else 0
        ref = np.zeros(n)
    for o in target_orbs:
        if up[o] is None:
            up[o] = np.zeros_like(ref)
        if is_spin and dn[o] is None:
            dn[o] = np.zeros_like(ref)
    return up, dn


def parse_doscar_spin_all(
    filepath: str,
    atoms_str: str,
    orbitals: Optional[List[str]] = None,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, np.ndarray], float]:
    """Parse DOSCAR -> (energy, rho_up, rho_dn, rho_total, efermi).

    ``rho_dn`` mirrors the raw VASP sign convention (negative magnitudes);
    ``rho_total`` combines magnitudes (``|up|+|dn|``).
    """
    target_orbs = list(orbitals) if orbitals else list(all_orb_names)
    energy, _total, per_atom, efermi, is_spin = _read_doscar_raw(filepath)

    struct = _load_structure_near(filepath)
    if struct is not None and len(struct) != len(per_atom):
        # Definite misalignment — indices would silently map to wrong atoms.
        raise DbandError(
            f"{filepath}: POSCAR/CONTCAR site count ({len(struct)}) != DOSCAR "
            f"PDOS ion count ({len(per_atom)}). Atom indices cannot be aligned "
            "— results would be meaningless. Ensure the DOSCAR ships with the "
            "matching POSCAR/CONTCAR from the same calculation."
        )

    if struct is not None:
        target_indices = _resolve_atom_indices(atoms_str, struct)
    else:
        # No structure file: only numeric indices are meaningful.
        target_indices = _resolve_numeric_indices(atoms_str, len(per_atom))

    layout = (_classify_pdos_layout(per_atom[0].shape[1], total_is_spin=is_spin)
              if per_atom else None)

    if layout is not None and layout.mode == "noncollinear":
        components = _accumulate_noncollinear(per_atom, target_indices, target_orbs)
        rho_up = {}
        rho_dn = {}
        rho_total = {}
        for orb in target_orbs:
            total = components["total"][orb]
            up, dn = _project_noncollinear_spin(total, components["m3"][orb])
            rho_up[orb] = up
            rho_dn[orb] = dn
            rho_total[orb] = total
        return energy, rho_up, rho_dn, rho_total, efermi

    up, dn = _accumulate(per_atom, is_spin, target_indices, target_orbs)

    if is_spin:
        rho_up = {o: np.abs(up[o]) for o in target_orbs}
        rho_dn = {o: np.abs(dn[o]) for o in target_orbs}
        rho_total = {o: rho_up[o] + rho_dn[o] for o in target_orbs}
    else:
        # Non-spin: only one channel; expose it as 'up' and 'total', 'down'=0.
        rho_up = {o: up[o] for o in target_orbs}
        rho_dn = {o: np.zeros_like(up[o]) for o in target_orbs}
        rho_total = {o: up[o] for o in target_orbs}

    return energy, rho_up, rho_dn, rho_total, efermi


def parse_doscar(
    filepath: str,
    atoms_str: str,
    spin_mode: str,
    orbitals: Optional[List[str]] = None,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], float]:
    """Parse DOSCAR -> (energy, rho_dict, efermi) for a single spin channel.

    ``spin_mode`` is one of ``"up"``, ``"down"``, ``"total"``.  For
    non-spin-polarised DOSCAR any mode returns the single channel.

    ``parse_doscar_spin_all`` already applies ``abs()`` at the boundary,
    so the values returned here are guaranteed non-negative magnitudes;
    no additional ``_ensure_positive`` call is needed.
    """
    energy, rho_up, rho_dn, rho_total, efermi = parse_doscar_spin_all(
        filepath, atoms_str, orbitals=orbitals)

    if spin_mode == "up":
        rho = rho_up
    elif spin_mode == "down":
        rho = rho_dn
    else:
        rho = rho_total  # already magnitude-summed
    return energy, rho, efermi


def _resolve_numeric_indices(atoms_str: str, n_blocks: int) -> List[int]:
    """Resolve a numeric-only atom selection without a structure file."""
    atoms_str = (atoms_str or "").strip()
    if not atoms_str:
        return list(range(n_blocks))
    target: List[int] = []
    for p in atoms_str.split(","):
        p = p.strip()
        if p.isdigit():
            idx = int(p) - 1
            if 0 <= idx < n_blocks:
                target.append(idx)
        elif "-" in p and p.split("-")[0].isdigit():
            lo, hi = p.split("-")[0], p.split("-")[-1]
            if lo.isdigit() and hi.isdigit():
                target.extend(range(int(lo) - 1, min(int(hi), n_blocks)))
    target = sorted(set(target))
    if not target:
        raise DbandError(
            f"Atom selection '{atoms_str}' matched no ions (1–{n_blocks}).")
    return target
