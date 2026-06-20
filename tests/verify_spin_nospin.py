"""
Comprehensive parser regression test: verifies both spin-polarised AND
non-spin-polarised paths for DOSCAR and vasprun.xml.

Covers the 4 combinations:
  1. DOSCAR spin-polarised (interleaved columns)
  2. DOSCAR non-spin-polarised (single channel)
  3. vasprun.xml spin-polarised (spin 1 + spin 2 sets)
  4. vasprun.xml non-spin-polarised (spin 1 only)

Run:  python tests/verify_spin_nospin.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.parsers.doscar import (
    _read_doscar_raw, _select_orbital_columns, _accumulate,
    _resolve_numeric_indices,
)
from core.parsers.constants import d_orb_names, all_orb_names
from core.calculator import calc_metrics

PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"
failures: list = []


def check(cond, label, detail=""):
    status = PASS if cond else FAIL
    line = f"  {status} {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    if not cond:
        failures.append(label)


def section(title):
    print(f"\n{'='*70}\n{title}\n{'='*70}")


# ── Synthetic Gaussian DOS for testing ──────────────────────────────
def make_gaussian_dos(energy, center, width, amplitude):
    """Generate a Gaussian-shaped DOS centred at `center` with given width."""
    return amplitude * np.exp(-0.5 * ((energy - center) / width) ** 2)


# ── 1. DOSCAR spin-polarised (interleaved) ──────────────────────────
def test_doscar_spin_polarised():
    section("1. DOSCAR spin-polarised (interleaved columns)")
    # Build a minimal DOSCAR: 1 ion, LORBIT=11 (9 orbs per channel),
    # interleaved: energy, s_up, s_dn, py_up, py_dn, ..., dx2-y2_up, dx2-y2_dn
    nedos = 301
    emin, emax = -15.0, 15.0
    energy = np.linspace(emin, emax, nedos)
    ef = 0.0

    # Synthesize DOS: dxy_up = Gaussian at -1 eV, dxy_dn = Gaussian at +1 eV
    # (artificial spin splitting for testing)
    orb_order = ["s", "py", "pz", "px", "dxy", "dyz", "dz2", "dxz", "dx2-y2"]
    up_data = {o: np.zeros(nedos) for o in orb_order}
    dn_data = {o: np.zeros(nedos) for o in orb_order}
    up_data["dxy"] = make_gaussian_dos(energy, -1.0, 1.0, 1.0)
    dn_data["dxy"] = make_gaussian_dos(energy, +1.0, 1.0, 0.3)
    # Add some s orbital (non-d) to verify filtering
    up_data["s"] = make_gaussian_dos(energy, -5.0, 0.5, 0.5)

    # Build per-atom block: energy, s_up, s_dn, py_up, py_dn, ...
    per_atom_rows = []
    for i in range(nedos):
        row = [energy[i]]
        for o in orb_order:
            row.append(up_data[o][i])
            row.append(dn_data[o][i])
        per_atom_rows.append(row)
    per_atom_arr = np.array(per_atom_rows)  # (nedos, 19) — energy + 18

    # Total DOS block: spin-polarised => 5 cols (energy, up, dn, int_up, int_dn)
    total_up = sum(up_data.values())
    total_dn = sum(dn_data.values())
    total_rows = []
    for i in range(nedos):
        total_rows.append([
            energy[i], total_up[i], total_dn[i],
            np.cumsum(total_up[:i+1])[-1] * (energy[1]-energy[0]),
            np.cumsum(total_dn[:i+1])[-1] * (energy[1]-energy[0]),
        ])
    total_arr = np.array(total_rows)

    # Verify _select_orbital_columns returns interleaved indices
    n_cols = per_atom_arr.shape[1] - 1  # strip energy
    col_map = _select_orbital_columns(n_cols, is_spin=True, target_orbs=d_orb_names)
    print(f"  {INFO} col_map for d-orbitals (interleaved): {col_map}")
    # Expect dxy: (8, 9) — s=0/1, py=2/3, pz=4/5, px=6/7, dxy=8/9
    check(col_map.get("dxy") == (8, 9),
          "dxy mapped to interleaved cols (8, 9)",
          f"got {col_map.get('dxy')}")

    # Run _accumulate
    up, dn = _accumulate([per_atom_arr[:, 1:]], True, [0], d_orb_names)

    # Verify dxy_up matches our synthetic input
    dxy_up_diff = np.max(np.abs(up["dxy"] - up_data["dxy"]))
    dxy_dn_diff = np.max(np.abs(dn["dxy"] - dn_data["dxy"]))
    check(dxy_up_diff < 1e-10, "dxy_up matches synthetic input",
          f"max_diff={dxy_up_diff:.2e}")
    check(dxy_dn_diff < 1e-10, "dxy_dn matches synthetic input",
          f"max_diff={dxy_dn_diff:.2e}")

    # Verify s orbital NOT in d-only result
    check("s" not in up, "s orbital excluded from d-only selection")

    # d-band center should be near -1 (up dominates)
    rho_up = {o: np.abs(up[o]) for o in d_orb_names}
    rho_dn = {o: np.abs(dn[o]) for o in d_orb_names}
    rho_total = {o: rho_up[o] + rho_dn[o] for o in d_orb_names}
    center, width, filling, _ = calc_metrics(energy, rho_total, ef=ef,
                                             orb_names=d_orb_names)
    # dxy dominates; its up peak is at -1, dn at +1 with 0.3 amplitude.
    # Weighted center ≈ (-1*1.0 + 1*0.3) / (1.0+0.3) ≈ -0.54
    check(-1.0 < center < 0.0, "d-band center in expected range",
          f"center={center:.4f}")
    print(f"  {INFO} synthetic d-band center={center:.4f} eV")


# ── 2. DOSCAR non-spin-polarised ────────────────────────────────────
def test_doscar_non_spin():
    section("2. DOSCAR non-spin-polarised (single channel)")
    nedos = 301
    energy = np.linspace(-15.0, 15.0, nedos)
    ef = 0.0

    # LORBIT=11 non-spin: energy, s, py, pz, px, dxy, dyz, dz2, dxz, dx2-y2 (10 cols)
    orb_order = ["s", "py", "pz", "px", "dxy", "dyz", "dz2", "dxz", "dx2-y2"]
    data = {o: np.zeros(nedos) for o in orb_order}
    data["dxy"] = make_gaussian_dos(energy, -1.0, 1.0, 1.0)
    data["s"] = make_gaussian_dos(energy, -5.0, 0.5, 0.5)

    per_atom_rows = [[energy[i]] + [data[o][i] for o in orb_order]
                     for i in range(nedos)]
    per_atom_arr = np.array(per_atom_rows)  # (nedos, 10)

    # Total DOS: non-spin => 3 cols (energy, total, integrated)
    total = sum(data.values())
    total_rows = [[energy[i], total[i],
                   np.cumsum(total[:i+1])[-1] * (energy[1]-energy[0])]
                  for i in range(nedos)]
    total_arr = np.array(total_rows)

    # is_spin detection: 3 cols (after energy strip) => non-spin
    is_spin = total_arr.shape[1] >= 4
    check(is_spin is False, "non-spin total DOS detected (3 cols)",
          f"is_spin={is_spin}")

    # col_map: non-spin => (ci,) tuples
    n_cols = per_atom_arr.shape[1] - 1
    col_map = _select_orbital_columns(n_cols, is_spin=False, target_orbs=d_orb_names)
    print(f"  {INFO} col_map (non-spin): {col_map}")
    # Expect dxy: (4,) — s=0, py=1, pz=2, px=3, dxy=4
    check(col_map.get("dxy") == (4,),
          "dxy mapped to single col (4) in non-spin",
          f"got {col_map.get('dxy')}")

    # _accumulate
    up, dn = _accumulate([per_atom_arr[:, 1:]], False, [0], d_orb_names)
    dxy_diff = np.max(np.abs(up["dxy"] - data["dxy"]))
    check(dxy_diff < 1e-10, "dxy matches synthetic input (non-spin)",
          f"max_diff={dxy_diff:.2e}")

    # dn should be None (no spin-down channel in non-spin)
    check(dn["dxy"] is None, "dn channel is None for non-spin DOSCAR")

    # Materialise: rho_up = |up|, rho_dn = zeros, rho_total = rho_up
    rho_up = {o: np.abs(up[o]) for o in d_orb_names}
    rho_dn = {o: np.zeros_like(rho_up[o]) for o in d_orb_names}
    rho_total = {o: rho_up[o] for o in d_orb_names}

    # has_spin detection: all rho_dn zero => non-spin
    has_spin = any(np.any(rho_dn[o] != 0) for o in d_orb_names)
    check(has_spin is False, "has_spin=False for non-spin DOSCAR")

    center, width, filling, _ = calc_metrics(energy, rho_total, ef=ef,
                                             orb_names=d_orb_names)
    # Only dxy has signal, centred at -1.0
    check(-1.5 < center < -0.5, "d-band center near -1.0 (dxy peak)",
          f"center={center:.4f}")
    print(f"  {INFO} non-spin d-band center={center:.4f} eV, filling={filling:.2f}%")


# ── 3. vasprun.xml spin-polarised ───────────────────────────────────
def test_vasprun_spin_polarised():
    section("3. vasprun.xml spin-polarised (spin 1 + spin 2 sets)")
    # Build a minimal vasprun.xml with 1 ion, 9 orbitals, spin-polarised.
    nedos = 101
    energy = np.linspace(-5.0, 5.0, nedos)
    ef = 0.0

    orb_fields = ["energy", "s", "py", "pz", "px", "dxy", "dyz", "dz2", "dxz", "dx2-y2"]
    # spin-up: dxy peak at -1; spin-down: dxy peak at +1
    up_dxy = make_gaussian_dos(energy, -1.0, 0.5, 1.0)
    dn_dxy = make_gaussian_dos(energy, +1.0, 0.5, 0.3)

    # Minimal vasprun.xml structure.  Note: must NOT include <generator>
    # with non-numeric <i> children — pymatgen's _parse_params tries to
    # coerce <i name="...">text</i> values to float, and will crash on
    # 'VASP_TEST'.  We omit <generator> entirely; the in-file structure
    # is parsed by our lxml fast path which doesn't need it.
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<modeling>')
    lines.append('  <incar><i name="ISPIN">2</i></incar>')
    # Structure (1 atom) — parsed by lxml fast path
    lines.append('  <structure name="finalpos">')
    lines.append('    <crystal><varray name="basis">')
    lines.append('      <v>10.0 0.0 0.0</v><v>0.0 10.0 0.0</v><v>0.0 0.0 10.0</v>')
    lines.append('    </varray></crystal>')
    lines.append('    <varray name="positions"><v>0.0 0.0 0.0</v></varray>')
    lines.append('    <array name="atoms" type="string" size="1"><set>')
    lines.append('      <rc><c>Mo</c></rc>')
    lines.append('    </set></array>')
    lines.append('  </structure>')
    lines.append(f'  <calculation><i name="efermi">{ef}</i>')
    # Total DOS — energies are parsed from here (spin 1 set, <r> first col).
    # For spin-polarised: 5 cols (energy, up, dn, int_up, int_dn).
    # NOTE: real vasprun.xml nests <total> and <partial> as siblings inside
    # one <dos>; do NOT open two <dos> tags.
    lines.append('    <dos>')
    lines.append('      <total><array name="dos"><set>')
    lines.append('        <set comment="spin 1">')
    for i in range(nedos):
        lines.append(f'          <r>{energy[i]:.6f} 1.0 0.5 0.0 0.0</r>')
    lines.append('        </set>')
    lines.append('      </set></array></total>')
    lines.append('      <partial>')
    # field names
    lines.append('        <field>' + '</field><field>'.join(orb_fields) + '</field>')
    # spin 1
    lines.append('        <set comment="spin 1"><set comment="ion 1">')
    for i in range(nedos):
        row = [f"{energy[i]:.6f}"]
        for o in orb_fields[1:]:
            if o == "dxy":
                row.append(f"{up_dxy[i]:.6f}")
            else:
                row.append("0.000000")
        lines.append('          <r>' + ' '.join(row) + '</r>')
    lines.append('        </set></set>')
    # spin 2
    lines.append('        <set comment="spin 2"><set comment="ion 1">')
    for i in range(nedos):
        row = [f"{energy[i]:.6f}"]
        for o in orb_fields[1:]:
            if o == "dxy":
                row.append(f"{dn_dxy[i]:.6f}")
            else:
                row.append("0.000000")
        lines.append('          <r>' + ' '.join(row) + '</r>')
    lines.append('        </set></set>')
    lines.append('      </partial>')
    lines.append('    </dos>')
    lines.append('  </calculation>')
    lines.append('</modeling>')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml',
                                     delete=False, encoding='utf-8') as f:
        f.write('\n'.join(lines))
        tmp_path = f.name

    try:
        from core.parsers.vasprun import parse_vasprun_spin_all
        e, rho_up, rho_dn, rho_total, efermi = parse_vasprun_spin_all(
            tmp_path, "Mo", orbitals=d_orb_names)

        check(np.isclose(efermi, ef), f"efermi matches ({efermi})")
        check(len(e) == nedos, f"energy length correct ({len(e)})")

        # dxy_up should match our synthetic up_dxy
        dxy_up_diff = np.max(np.abs(rho_up["dxy"] - np.abs(up_dxy)))
        dxy_dn_diff = np.max(np.abs(rho_dn["dxy"] - np.abs(dn_dxy)))
        check(dxy_up_diff < 1e-6, "dxy_up matches synthetic (vasprun spin)",
              f"max_diff={dxy_up_diff:.2e}")
        check(dxy_dn_diff < 1e-6, "dxy_dn matches synthetic (vasprun spin)",
              f"max_diff={dxy_dn_diff:.2e}")

        # rho_total = rho_up + rho_dn
        for o in d_orb_names:
            diff = np.max(np.abs(rho_total[o] - (rho_up[o] + rho_dn[o])))
            check(diff < 1e-10, f"rho_total[{o}] == rho_up + rho_dn")

        center, width, filling, _ = calc_metrics(e, rho_total, ef=efermi,
                                                 orb_names=d_orb_names)
        check(-1.0 < center < 0.0, "d-band center in expected range",
              f"center={center:.4f}")
        print(f"  {INFO} vasprun spin d-band center={center:.4f} eV")
    finally:
        try:
            os.unlink(tmp_path)
        except (PermissionError, OSError):
            pass  # Windows may hold the file briefly


# ── 4. vasprun.xml non-spin-polarised ───────────────────────────────
def test_vasprun_non_spin():
    section("4. vasprun.xml non-spin-polarised (spin 1 only)")
    nedos = 101
    energy = np.linspace(-5.0, 5.0, nedos)
    ef = 0.0

    orb_fields = ["energy", "s", "py", "pz", "px", "dxy", "dyz", "dz2", "dxz", "dx2-y2"]
    dxy = make_gaussian_dos(energy, -1.0, 0.5, 1.0)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<modeling>')
    lines.append('  <incar><i name="ISPIN">1</i></incar>')
    lines.append('  <structure name="finalpos">')
    lines.append('    <crystal><varray name="basis">')
    lines.append('      <v>10.0 0.0 0.0</v><v>0.0 10.0 0.0</v><v>0.0 0.0 10.0</v>')
    lines.append('    </varray></crystal>')
    lines.append('    <varray name="positions"><v>0.0 0.0 0.0</v></varray>')
    lines.append('    <array name="atoms" type="string" size="1"><set>')
    lines.append('      <rc><c>Mo</c></rc>')
    lines.append('    </set></array>')
    lines.append('  </structure>')
    lines.append(f'  <calculation><i name="efermi">{ef}</i>')
    # Total DOS — energies are parsed from here (spin 1 set, <r> first col).
    # Non-spin: 3 cols (energy, total, integrated).
    lines.append('    <dos>')
    lines.append('      <total><array name="dos"><set>')
    lines.append('        <set comment="spin 1">')
    for i in range(nedos):
        lines.append(f'          <r>{energy[i]:.6f} 1.0 0.0</r>')
    lines.append('        </set>')
    lines.append('      </set></array></total>')
    lines.append('      <partial>')
    lines.append('        <field>' + '</field><field>'.join(orb_fields) + '</field>')
    # ONLY spin 1, no spin 2 (non-spin-polarised)
    lines.append('        <set comment="spin 1"><set comment="ion 1">')
    for i in range(nedos):
        row = [f"{energy[i]:.6f}"]
        for o in orb_fields[1:]:
            if o == "dxy":
                row.append(f"{dxy[i]:.6f}")
            else:
                row.append("0.000000")
        lines.append('          <r>' + ' '.join(row) + '</r>')
    lines.append('        </set></set>')
    lines.append('      </partial>')
    lines.append('    </dos>')
    lines.append('  </calculation>')
    lines.append('</modeling>')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml',
                                     delete=False, encoding='utf-8') as f:
        f.write('\n'.join(lines))
        tmp_path = f.name

    try:
        from core.parsers.vasprun import parse_vasprun_spin_all
        e, rho_up, rho_dn, rho_total, efermi = parse_vasprun_spin_all(
            tmp_path, "Mo", orbitals=d_orb_names)

        check(np.isclose(efermi, ef), f"efermi matches ({efermi})")
        check(len(e) == nedos, f"energy length correct ({len(e)})")

        # dxy_up should match synthetic; dxy_dn should be ALL ZEROS
        dxy_up_diff = np.max(np.abs(rho_up["dxy"] - np.abs(dxy)))
        check(dxy_up_diff < 1e-6, "dxy_up matches synthetic (vasprun non-spin)",
              f"max_diff={dxy_up_diff:.2e}")

        dxy_dn_max = np.max(np.abs(rho_dn["dxy"]))
        check(dxy_dn_max < 1e-12, "dxy_dn is all zeros (non-spin vasprun)",
              f"max={dxy_dn_max:.2e}")

        # All dn orbitals should be zero
        all_dn_zero = all(np.max(np.abs(rho_dn[o])) < 1e-12 for o in d_orb_names)
        check(all_dn_zero, "all rho_dn orbitals zero (non-spin vasprun)")

        # rho_total == rho_up (since dn is zero)
        for o in d_orb_names:
            diff = np.max(np.abs(rho_total[o] - rho_up[o]))
            check(diff < 1e-10, f"rho_total[{o}] == rho_up (non-spin)")

        # _detect_has_spin should return False
        from core.parsers.common import _detect_has_spin
        has_spin = _detect_has_spin(rho_dn)
        check(has_spin is False, "_detect_has_spin returns False (non-spin vasprun)")

        center, width, filling, _ = calc_metrics(e, rho_total, ef=efermi,
                                                 orb_names=d_orb_names)
        check(-1.5 < center < -0.5, "d-band center near -1.0 (dxy peak)",
              f"center={center:.4f}")
        print(f"  {INFO} vasprun non-spin d-band center={center:.4f} eV, "
              f"filling={filling:.2f}%")
    finally:
        try:
            os.unlink(tmp_path)
        except (PermissionError, OSError):
            pass


if __name__ == "__main__":
    print("Comprehensive parser regression: spin + non-spin, DOSCAR + vasprun")
    print(f"Python {sys.version.split()[0]}, numpy {np.__version__}")

    test_doscar_spin_polarised()
    test_doscar_non_spin()
    test_vasprun_spin_polarised()
    test_vasprun_non_spin()

    section("SUMMARY")
    if failures:
        print(f"  {FAIL} {len(failures)} check(s) failed:")
        for f in failures:
            print(f"      - {f}")
        sys.exit(1)
    else:
        print(f"  {PASS} all 4 combinations verified (DOSCAR/vasprun × spin/non-spin)")
        sys.exit(0)
