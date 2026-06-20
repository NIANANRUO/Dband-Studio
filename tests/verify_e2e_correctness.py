"""Optional, auditable real-DOS regression.

Set ``DBAND_REAL_DOSCAR`` to a local DOSCAR.  The script never modifies the
input and reports both the physical parser metadata and d-band centers using
the explicit, Fermi-referenced integration window supplied through
``DBAND_WINDOW`` (default: ``-12.75,12.25``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.calculator import calc_metrics
from core.loader import DataLoader
from core.parsers.constants import d_orb_names


def main() -> int:
    path_text = os.environ.get("DBAND_REAL_DOSCAR")
    if not path_text:
        print("SKIP: set DBAND_REAL_DOSCAR to run real-data verification.")
        return 0
    path = Path(path_text)
    if not path.is_file():
        raise SystemExit(f"ERROR: DOSCAR does not exist: {path}")

    before = (path.stat().st_size, path.stat().st_mtime_ns)
    window = tuple(float(value) for value in os.environ.get(
        "DBAND_WINDOW", "-12.75,12.25").split(","))
    if len(window) != 2 or window[0] >= window[1]:
        raise SystemExit("ERROR: DBAND_WINDOW must be 'emin,emax' with emin < emax.")

    energy, up, down, _total, ef, metadata = DataLoader.load_spin_all_with_metadata(
        str(path), "", orbitals=d_orb_names + ["d"])
    orbital_names = ["d"] if "d" in up and any(up["d"] != 0) else d_orb_names
    up_center = calc_metrics(
        energy, up, ef, orb_names=orbital_names, custom_range=window,
        method="trapezoid")[0]
    down_center = calc_metrics(
        energy, down, ef, orb_names=orbital_names, custom_range=window,
        method="trapezoid")[0]
    after = (path.stat().st_size, path.stat().st_mtime_ns)
    if before != after:
        raise SystemExit("ERROR: input DOSCAR metadata changed during a read-only verification.")

    print(f"source={path}")
    print(f"metadata={metadata}")
    print(f"fermi_eV={ef:.8f}")
    print(f"window_relative_to_fermi_eV={window}")
    print(f"d_band_center_up_eV={up_center:.8f}")
    print(f"d_band_center_down_eV={down_center:.8f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
