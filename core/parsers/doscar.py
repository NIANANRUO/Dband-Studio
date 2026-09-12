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
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.exceptions import (
    AmbiguousLayoutError, AtomSelectionError, DbandError, FileIntegrityError,
    StructureMismatchError, UnsupportedLayoutError,
)
from core.pdos_metadata import PDOSCapabilities, PDOSInputContext, PDOSMetadata
from core.parsers.common import (
    _load_structure_file,
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


def _metadata_noncollinear_hint(
    filepath: str, *, metadata_path: Optional[str] = None,
) -> Optional[bool]:
    """Read explicitly authorized metadata for an ambiguous DOSCAR row.

    DOSCAR does not encode LORBIT separately.  A 16-column non-spin total
    row is therefore ambiguous between LORBIT=11 scalar DOS and LORBIT=10
    noncollinear four-component DOS.  Prefer ``vasprun.xml`` because it is
    generated output or INCAR may be supplied explicitly. If no authorized
    metadata records the flags, callers reject the layout instead of guessing.
    """
    if not metadata_path:
        return None
    values: Dict[str, bool] = {}
    candidate = metadata_path
    filename = os.path.basename(candidate)
    if os.path.isfile(candidate):
        try:
            with open(candidate, "r", encoding="utf-8", errors="ignore") as fh:
                for line_number, line in enumerate(fh):
                    for name in ("LNONCOLLINEAR", "LSORBIT"):
                        incar_match = re.match(
                            rf"^\s*{name}\s*=\s*([^\s!#]+)", line, flags=re.IGNORECASE)
                        xml_match = re.search(
                            rf'name=["\']{name}["\'][^>]*>\s*([^<\s]+)',
                            line, flags=re.IGNORECASE)
                        match = incar_match or xml_match
                        if match:
                            value = match.group(1).strip().strip(".").upper()
                            if value in {"T", "TRUE"}:
                                values[name] = True
                            elif value in {"F", "FALSE"}:
                                values[name] = False
                    # VASP parameters appear in the initial XML section;
                    # avoid scanning an enormous DOS payload solely for tags.
                    if filename == "vasprun.xml" and line_number > 20000:
                        break
        except OSError:
            pass

    if values.get("LNONCOLLINEAR") is True or values.get("LSORBIT") is True:
        return True

    if values:
        return False
    return None


def _metadata_saxis(
    filepath: str, *, metadata_path: Optional[str] = None,
) -> Tuple[float, float, float]:
    """Return SAXIS from an authorized file, or VASP's default (0,0,1)."""
    candidate = metadata_path
    if candidate and os.path.isfile(candidate):
        filename = os.path.basename(candidate)
        try:
            with open(candidate, "r", encoding="utf-8", errors="ignore") as fh:
                for line_number, line in enumerate(fh):
                    incar_match = re.match(r"^\s*SAXIS\s*=\s*(.*)$", line, flags=re.IGNORECASE)
                    xml_match = re.search(r'name=["\']SAXIS["\'][^>]*>\s*([^<]+)', line, flags=re.IGNORECASE)
                    match = incar_match or xml_match
                    if match:
                        try:
                            values = np.asarray(match.group(1).split()[:3], dtype=np.float64)
                        except ValueError as exc:
                            raise DbandError(f"{candidate}: SAXIS is not three numeric values.") from exc
                        if values.shape != (3,) or not np.isfinite(values).all():
                            raise DbandError(f"{candidate}: SAXIS is not three finite values.")
                        norm = np.linalg.norm(values)
                        if norm == 0:
                            raise DbandError(f"{candidate}: SAXIS must not be the zero vector.")
                        return tuple((values / norm).tolist())
                    if filename == "vasprun.xml" and line_number > 20000:
                        break
        except OSError:
            pass
    return (0.0, 0.0, 1.0)


@dataclass(frozen=True)
class PDOSLayout:
    """Physical interpretation of one DOSCAR site-projected data row."""

    mode: str
    orbital_resolution: str
    orbitals: Tuple[str, ...]
    components: Tuple[str, ...]


def _classify_pdos_layout(
    n_cols: int,
    *,
    total_is_spin: bool,
    noncollinear_hint: Optional[bool] = None,
) -> PDOSLayout:
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
        scalar = None
        noncollinear = None
        if n_cols in lm_counts:
            scalar = PDOSLayout("nonspin", "lm", tuple(_LORBIT11_ORBS[:n_cols]),
                                ("total",))
        elif n_cols in l_counts:
            scalar = PDOSLayout("nonspin", "l", tuple(_LORBIT10_ORBS),
                                ("total",))
        if n_cols % 4 == 0:
            count = n_cols // 4
            if count in lm_counts:
                noncollinear = PDOSLayout("noncollinear", "lm",
                                           tuple(_LORBIT11_ORBS[:count]),
                                           ("total", "m1", "m2", "m3"))
            elif count in l_counts:
                noncollinear = PDOSLayout("noncollinear", "l", tuple(_LORBIT10_ORBS),
                                           ("total", "m1", "m2", "m3"))

        if scalar is not None and noncollinear is not None:
            if noncollinear_hint is None:
                raise AmbiguousLayoutError(
                    "DOSCAR", n_cols,
                    "Provide matching INCAR or vasprun.xml metadata "
                    "(LNONCOLLINEAR/LSORBIT).")
            return noncollinear if noncollinear_hint else scalar
        if noncollinear is not None:
            if noncollinear_hint is False:
                raise DbandError(
                    "Projected DOS has noncollinear total/m1/m2/m3 columns but "
                    "nearby calculation metadata declares LNONCOLLINEAR=F and LSORBIT=F.")
            return noncollinear
        if scalar is not None:
            if noncollinear_hint is True:
                raise DbandError(
                    "Nearby calculation metadata declares noncollinear/SOC, but "
                    "the projected DOS has no total/m1/m2/m3 components.")
            return scalar

    raise UnsupportedLayoutError(
        "DOSCAR", n_cols,
        "Refusing to guess orbital or spin-column mapping.")


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
    per_atom: List[np.ndarray],
    target_indices: List[int],
    target_orbs: List[str],
    *,
    noncollinear_hint: Optional[bool] = None,
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
        layout = _classify_pdos_layout(
            arr.shape[1], total_is_spin=False, noncollinear_hint=noncollinear_hint)
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
        raise FileIntegrityError(f"{filepath}: DOSCAR too short ({len(lines)} lines).")

    header = lines[5].split()
    if len(header) < 5:
        raise FileIntegrityError(
            f"{filepath}: malformed DOSCAR header line 6: {lines[5]!r}")
    try:
        nedos = int(float(header[2]))
        efermi = float(header[3])
    except (ValueError, IndexError):
        raise FileIntegrityError(
            f"{filepath}: cannot read NEDOS/EFERMI from header: {lines[5]!r}")

    # Total DOS block.
    total_start = 6
    total_block = lines[total_start:total_start + nedos]
    if len(total_block) < nedos:
        raise FileIntegrityError(
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
            raise FileIntegrityError(
                f"Invalid numeric value in {context}: {ln!r}") from exc
        if width == 0:
            width = len(row)
        elif len(row) != width:
            # Ragged row — stop to avoid silently misaligning columns.
            raise FileIntegrityError(
                f"Ragged {context}: expected {width} columns, "
                f"got {len(row)} in row {len(rows) + 1}.")
        rows.append(row)
    if not rows:
        raise FileIntegrityError(f"No numeric data found in {context}.")
    if expected_rows is not None and len(rows) != expected_rows:
        raise FileIntegrityError(
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
    *,
    return_metadata: bool = False,
    input_context: Optional[PDOSInputContext] = None,
    per_atom_output: Optional[dict] = None,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, np.ndarray], float]:
    """Parse DOSCAR -> (energy, rho_up, rho_dn, rho_total, efermi).

    ``rho_dn`` mirrors the raw VASP sign convention (negative magnitudes);
    ``rho_total`` combines magnitudes (``|up|+|dn|``).
    """
    context = input_context or PDOSInputContext(filepath, "DOSCAR")
    target_orbs = list(orbitals) if orbitals else list(all_orb_names)
    energy, _total, per_atom, efermi, is_spin = _read_doscar_raw(filepath)
    if not per_atom:
        raise FileIntegrityError(
            f"{filepath}: DOSCAR contains no site-projected DOS blocks. "
            "Set LORBIT=10 or LORBIT=11 and rerun VASP.")

    def finish(rho_up, rho_dn, rho_total, *, mode: str, resolution: str):
        result = (energy, rho_up, rho_dn, rho_total, efermi)
        if not return_metadata:
            return result
        axis = (_metadata_saxis(
            filepath, metadata_path=context.metadata_path)
            if mode == "noncollinear" else None)
        warnings = () if struct is not None else (
            "No structure file was authorized; use numeric indices or select one explicitly.",)
        capabilities = PDOSCapabilities(
            source_format="DOSCAR", vasp_version=None, spin_mode=mode,
            orbital_resolution=resolution,
            available_orbitals=layout.orbitals if layout else (),
            structure_available=struct is not None,
            atom_selection_modes=("index", "element") if struct is not None else ("index",),
            field_source="doscar_layout", warnings=warnings)
        return (*result, PDOSMetadata(
            mode=mode, orbital_resolution=resolution, spin_axis=axis,
            source_format="DOSCAR", capabilities=capabilities))

    struct = None
    if context.structure_path:
        try:
            struct = _load_structure_file(context.structure_path)
        except Exception as exc:
            raise FileIntegrityError(
                f"Cannot read explicitly selected structure "
                f"'{context.structure_path}': {exc}") from exc
    if struct is not None and len(struct) != len(per_atom):
        # Definite misalignment — indices would silently map to wrong atoms.
        raise StructureMismatchError(
            f"{filepath}: explicitly selected structure '{context.structure_path}' "
            f"has {len(struct)} sites but DOSCAR "
            f"PDOS ion count ({len(per_atom)}). Atom indices cannot be aligned "
            "— results would be meaningless. Ensure the DOSCAR ships with the "
            "explicitly selected structure from the same calculation."
        )

    if struct is not None:
        target_indices = _resolve_atom_indices(atoms_str, struct)
    else:
        # No structure file: only numeric indices are meaningful.
        target_indices = _resolve_numeric_indices(atoms_str, len(per_atom))

    noncollinear_hint = _metadata_noncollinear_hint(
        filepath, metadata_path=context.metadata_path)
    layout = (_classify_pdos_layout(
        per_atom[0].shape[1], total_is_spin=is_spin,
        noncollinear_hint=noncollinear_hint)
              if per_atom else None)

    if per_atom_output is not None:
        for idx in target_indices:
            if layout is not None and layout.mode == "noncollinear":
                components_i = _accumulate_noncollinear(
                    per_atom, [idx], target_orbs, noncollinear_hint=noncollinear_hint)
                up_i, dn_i = {}, {}
                for orb in target_orbs:
                    up_i[orb], dn_i[orb] = _project_noncollinear_spin(
                        components_i["total"][orb], components_i["m3"][orb])
            else:
                raw_up, raw_dn = _accumulate(per_atom, is_spin, [idx], target_orbs)
                up_i = {o: np.abs(raw_up[o]) for o in target_orbs}
                dn_i = {o: np.abs(raw_dn[o]) if is_spin else np.zeros_like(energy) for o in target_orbs}
            per_atom_output[idx + 1] = (energy, up_i, dn_i,
                {o: up_i[o] + dn_i[o] for o in target_orbs}, efermi)

    if layout is not None and layout.mode == "noncollinear":
        components = _accumulate_noncollinear(
            per_atom, target_indices, target_orbs,
            noncollinear_hint=noncollinear_hint)
        rho_up = {}
        rho_dn = {}
        rho_total = {}
        for orb in target_orbs:
            total = components["total"][orb]
            up, dn = _project_noncollinear_spin(total, components["m3"][orb])
            rho_up[orb] = up
            rho_dn[orb] = dn
            rho_total[orb] = total
        return finish(rho_up, rho_dn, rho_total,
                      mode="noncollinear", resolution=layout.orbital_resolution)

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

    return finish(rho_up, rho_dn, rho_total,
                  mode="collinear" if is_spin else "nonspin",
                  resolution=layout.orbital_resolution if layout else "unknown")


def parse_doscar(
    filepath: str,
    atoms_str: str,
    spin_mode: str,
    orbitals: Optional[List[str]] = None,
    *,
    input_context: Optional[PDOSInputContext] = None,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], float]:
    """Parse DOSCAR -> (energy, rho_dict, efermi) for a single spin channel.

    ``spin_mode`` is one of ``"up"``, ``"down"``, ``"total"``.  For
    non-spin-polarised DOSCAR any mode returns the single channel.

    ``parse_doscar_spin_all`` already applies ``abs()`` at the boundary,
    so the values returned here are guaranteed non-negative magnitudes;
    no additional ``_ensure_positive`` call is needed.
    """
    energy, rho_up, rho_dn, rho_total, efermi = parse_doscar_spin_all(
        filepath, atoms_str, orbitals=orbitals, input_context=input_context)

    if spin_mode == "up":
        rho = rho_up
    elif spin_mode == "down":
        rho = rho_dn
    else:
        rho = rho_total  # already magnitude-summed
    return energy, rho, efermi


def _resolve_numeric_indices(atoms_str: str, n_blocks: int) -> List[int]:
    """Resolve numeric selections strictly when no structure is authorized."""
    from core.parsers.common import resolve_selection
    return resolve_selection(atoms_str, n_blocks)
