"""VASPKIT PDOS parser."""

from __future__ import annotations

import os
import re
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.exceptions import AtomNotFoundError, DbandError, VASPKitAtomError
from core.parsers.common import _detect_has_spin, _load_structure_near, _site_symbol
from core.parsers.constants import all_orb_names

_logger = logging.getLogger("dband.parsers")

# ---- VASPKIT orbital aliases ----
_VASPKIT_ALIAS = {
    "s": "s",
    "py": "py", "pz": "pz", "px": "px",
    "dxy": "dxy", "dyz": "dyz", "dz2": "dz2", "dz^2": "dz2",
    "dxz": "dxz", "dx2-y2": "dx2-y2", "dx2": "dx2-y2",
    "x2-y2": "dx2-y2", "dx2y2": "dx2-y2",
    "f-3": "f-3", "f-2": "f-2", "f-1": "f-1",
    "f0": "f0", "f1": "f1", "f2": "f2", "f3": "f3",
    "fy(3x2-y2)": "f-3", "fxyz": "f-2", "fyz2": "f-1",
    "fz3": "f0", "fxz2": "f1", "fz(x2-y2)": "f2", "fx(x2-3y2)": "f3",
}

_VASPKIT_POSITIONAL = [
    "s", "py", "pz", "px",
    "dxy", "dyz", "dz2", "dxz", "dx2-y2",
    "f-3", "f-2", "f-1", "f0", "f1", "f2", "f3",
]


def _read_vaspkit_blocks(filepath: str):
    """Read VASPKIT PDOS file -> list of (energy, rho_dict) per atom block.

    Streams the file line-by-line instead of ``readlines()`` to keep peak
    memory low on large PDOS exports (multi-MB files with many atoms).
    """
    headers: list = []  # (header_cols, data_start_line_idx, data_end_line_idx)
    line_index = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            stripped = line.replace("#", "").strip()
            if re.search(r"(?i)energy", stripped):
                if headers:
                    headers[-1] = (headers[-1][0], headers[-1][1], i)
                headers.append((stripped.split(), i + 1, -1))

    if not headers:
        # No header found: scan for first non-comment line as the start.
        start = 0
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if line.strip() and not line.strip().startswith("#"):
                    start = i
                    break
        headers = [([], start, -1)]

    # Finalise the last header's end at EOF.
    with open(filepath, "r", encoding="utf-8") as f:
        n_lines = sum(1 for _ in f)
    if headers:
        headers[-1] = (headers[-1][0], headers[-1][1], n_lines)

    results: list = []
    for header_cols, data_start, data_end in headers:
        # Read only this block's slice to avoid loading the whole file.
        block_lines: list = []
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < data_start or i >= data_end:
                    continue
                s = line.strip()
                if s and not s.startswith("#"):
                    block_lines.append(s)
        if not block_lines:
            continue
        try:
            data = np.loadtxt(block_lines)
        except (ValueError, OSError) as e:
            raise DbandError(
                f"Failed to parse VASPKIT numeric block ({data_start}-{data_end}): {e}"
            ) from e
        if data.ndim == 1:
            data = data.reshape(1, -1)
        e = data[:, 0]
        ncols = data.shape[1]

        rho: Dict[str, np.ndarray] = {}
        col_names = header_cols[1:] if len(header_cols) > 1 else []
        header_matched = False

        # VASPKIT standard output (vaspkit -task 11x) stores spin-down as
        # negative values, whether in a separate _DW file (split format) or
        # a combined column.  abs() is therefore required to prevent
        # cancellation when summing channels.  For non-spin-polarised files
        # all values are already non-negative, so abs() is a no-op.
        #
        # abs() is intentionally applied here (not deferred) because:
        #   - VASPKIT -task 11/111 (PDOS): UP ≥ 0, DW ≤ 0  (verified)
        #   - VASPKIT -task 115/116 (net spin density): NOT standard PDOS;
        #     such files should NOT be fed to this parser.
        #   - User-processed "net" files (signed up+down in one column) are
        #     outside VASPKIT's output contract and will have their negative
        #     regions flipped to positive, overestimating the total.  Users
        #     must pre-process such files before loading.
        for ci, cname in enumerate(col_names):
            clean = re.sub(r"(?i)[_(](up|dw|dn|down|alpha|beta)[_)]?", "", cname).strip()
            matched = _VASPKIT_ALIAS.get(clean)
            if matched and (ci + 1) < ncols:
                if matched not in rho:
                    rho[matched] = np.zeros_like(e)
                rho[matched] += np.abs(data[:, ci + 1])
                header_matched = True

        if not header_matched:
            for j, oname in enumerate(_VASPKIT_POSITIONAL):
                col = j + 1
                if col < ncols:
                    rho[oname] = np.abs(data[:, col])

        results.append((e, rho))

    return results


def _resolve_atom_indices_vaspkit(
    filepath: str, atoms_str: str, n_blocks: int
) -> list:
    """Resolve atom selection for VASPKIT multi-atom PDOS."""
    if not atoms_str.strip():
        return list(range(n_blocks))

    target: list = []
    parts = [p.strip() for p in atoms_str.split(",")]
    struct = None

    for p in parts:
        if re.match(r"^\d+$", p):
            idx = int(p) - 1
            if 0 <= idx < n_blocks:
                target.append(idx)
        elif re.match(r"^\d+-\d+$", p):
            start, end = map(int, p.split("-"))
            target.extend(range(start - 1, min(end, n_blocks)))
        else:
            if struct is None:
                struct = _load_structure_near(filepath)
            if struct is None:
                raise VASPKitAtomError(atoms_str, n_blocks)
            for i, site in enumerate(struct):
                if i >= n_blocks:
                    break
                if _site_symbol(site) == p:
                    target.append(i)

    target = sorted(set(target))
    if not target:
        available = (
            [str(i + 1) for i in range(n_blocks)]
            if struct is None
            else sorted(set(_site_symbol(s) for s in struct))
        )
        raise AtomNotFoundError(atoms_str, available_species=available)
    return target


def _detect_spin_channel(filepath: str) -> str:
    """Detect spin channel from filename (case-insensitive regex)."""
    bn = os.path.basename(filepath)
    if re.search(r"(_u|_up|_alpha|spinup|_1)(\.[^.]+)?$", bn, re.IGNORECASE):
        return "up"
    if re.search(r"(_d|_dn|_dw|_down|spindn|spindw|_beta|_2)(\.[^.]+)?$", bn, re.IGNORECASE):
        return "down"
    return "unknown"


def _find_spin_partner(filepath: str) -> Optional[str]:
    """Find the spin-partner file via regex substitution.

    Supports common naming conventions: ``_u/_d``, ``_up/_dw``,
    ``_alpha/_beta``, ``_1/_2``, case-insensitive.  More extensible
    than the previous hardcoded 12-pair lookup.
    """
    bn = os.path.basename(filepath)
    d = os.path.dirname(filepath)

    # Split extension so suffix matching targets the stem only.
    stem, dot, ext = bn.rpartition(".")
    if not dot:  # no extension
        stem, ext = bn, ""

    # Ordered (up_pattern, down_replacement) and the reverse.  Match the
    # longest suffix first so ``_up`` does not shadow ``_u``.
    transforms = [
        ("_up", "_dw"), ("_UP", "_DW"),
        ("_up", "_dn"), ("_UP", "_DN"),
        ("_up", "_down"), ("_UP", "_DOWN"),
        ("_u", "_d"),   ("_U", "_D"),
        ("_alpha", "_beta"), ("_ALPHA", "_BETA"),
        ("_1", "_2"),   ("_spinup", "_spindn"),
        ("_SPINUP", "_SPINDN"),
        # Reverse direction (file is down, look for up)
        ("_dw", "_up"), ("_DW", "_UP"),
        ("_dn", "_up"), ("_DN", "_UP"),
        ("_down", "_up"), ("_DOWN", "_UP"),
        ("_d", "_u"),   ("_D", "_U"),
        ("_beta", "_alpha"), ("_BETA", "_ALPHA"),
        ("_2", "_1"),   ("_spindn", "_spinup"),
        ("_SPINDN", "_SPINUP"),
    ]
    for src, dst in transforms:
        if stem.endswith(src):
            new_stem = stem[:-len(src)] + dst
            new_bn = new_stem + (("." + ext) if ext else "")
            p = os.path.join(d, new_bn)
            if os.path.exists(p):
                return p
    return None


def _assert_same_energy_axis(
    ref: np.ndarray,
    other: np.ndarray,
    *,
    ref_label: str,
    other_label: str,
) -> None:
    """Reject PDOS blocks/channels whose DOS values are on different grids."""
    if ref.shape != other.shape or not np.allclose(ref, other, rtol=1e-10, atol=1e-12):
        raise DbandError(
            f"VASPKIT PDOS energy axis mismatch between {ref_label} and "
            f"{other_label}; refusing to combine unrelated DOS bins.")


def parse_vaspkit(
    filepath: str,
    spin_mode: str,
    atoms_str: str = "",
    orbitals: Optional[List[str]] = None,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], float]:
    """Parse VASPKIT PDOS file -> (energy, rho_dict, ef)."""
    energy, rho_up, rho_dn, _rho_total, ef = parse_vaspkit_spin_all(
        filepath, atoms_str, orbitals=orbitals)
    if spin_mode == "up":
        return energy, rho_up, ef
    elif spin_mode == "down":
        return energy, rho_dn, ef
    else:
        # total = |up| + |dn|; for non-spin files rho_dn is zeros so total == up
        rho_total = {o: rho_up.get(o, np.zeros_like(energy))
                     + rho_dn.get(o, np.zeros_like(energy))
                     for o in (orbitals or all_orb_names)}
        return energy, rho_total, ef


def parse_vaspkit_spin_all(
    filepath: str,
    atoms_str: str = "",
    orbitals: Optional[List[str]] = None,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, np.ndarray], float]:
    """Parse VASPKIT PDOS -> (energy, rho_up, rho_dn, rho_total, ef) in one pass.

    Single-file (non-spin) VASPKIT output has no spin label in its filename.
    For such files ``rho_dn`` is returned as all-zeros and ``rho_total == rho_up``,
    so downstream ``has_spin`` detection correctly reports False.  This avoids
    the previous double-load fallback that silently treated non-spin files as
    spin-polarised (rho_up == rho_dn).

    For spin-polarised files (filename contains ``_UP``/``_DW`` etc.), the
    partner file is located and both channels are returned with ``ef=0.0``
    (VASPKIT PDOS files never embed the Fermi level).
    """
    ef = 0.0
    target_orbs = list(orbitals) if orbitals else list(all_orb_names)
    ch = _detect_spin_channel(filepath)

    def _load_selected(fp: str) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        blocks = _read_vaspkit_blocks(fp)
        if not blocks:
            raise DbandError(f"No data in VASPKIT file: {fp}")
        energy = blocks[0][0]
        if len(blocks) == 1:
            if atoms_str.strip():
                _logger.warning(
                    "%s: atom selection ignored — single-block (system total) PDOS", fp)
            selected = [0]
        else:
            selected = _resolve_atom_indices_vaspkit(fp, atoms_str, len(blocks))
        rho: Dict[str, np.ndarray] = {o: np.zeros_like(energy) for o in target_orbs}
        for idx in selected:
            if idx >= len(blocks):
                _logger.warning("%s: atom idx %d > %d blocks, skipping", fp, idx, len(blocks))
                continue
            block_energy, b_rho = blocks[idx]
            _assert_same_energy_axis(
                energy, block_energy,
                ref_label=f"{fp} block 1",
                other_label=f"{fp} block {idx + 1}",
            )
            for o in target_orbs:
                if o in b_rho:
                    rho[o] += b_rho[o]
        return energy, rho

    energy, rho_up = _load_selected(filepath)

    if ch == "unknown":
        # Non-spin-polarised file: rho_dn is genuinely zero.
        rho_dn = {o: np.zeros_like(energy) for o in target_orbs}
        rho_total = {o: rho_up[o].copy() for o in target_orbs}
        return energy, rho_up, rho_dn, rho_total, ef

    # Spin-polarised: locate the partner channel.
    partner = _find_spin_partner(filepath)
    if partner is None:
        _logger.warning(
            "%s: spin channel '%s' has no partner file; treating as non-spin.",
            filepath, ch)
        rho_dn = {o: np.zeros_like(energy) for o in target_orbs}
        rho_total = {o: rho_up[o].copy() for o in target_orbs}
        return energy, rho_up, rho_dn, rho_total, ef

    partner_energy, rho_partner = _load_selected(partner)
    _assert_same_energy_axis(
        energy, partner_energy,
        ref_label=filepath,
        other_label=partner,
    )
    if ch == "up":
        rho_dn = rho_partner
    else:  # ch == "down"
        rho_dn = rho_up
        rho_up = rho_partner

    # Magnetic systems: total DOS must be |ρ_up| + |ρ_dw| (weighted
    # synthesis per the Hammer–Nørskov d-band formula), NOT a simple sum
    # which would cancel signed spin-down contributions.
    rho_total = {o: np.abs(rho_up[o]) + np.abs(rho_dn[o]) for o in target_orbs}
    return energy, rho_up, rho_dn, rho_total, ef
