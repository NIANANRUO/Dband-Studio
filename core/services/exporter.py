"""
Unified data export service for CSV and figure export.

Extracted from main_window.py and hybridization_win.py to centralize
all export logic in one place.
"""
from __future__ import annotations

import csv
from typing import List

import numpy as np

from core.parsers import d_orb_names
from models.results import DbandResult


class DataExporter:
    """Static service for exporting results and figures."""

    @staticmethod
    def export_results_csv(results_data: List[DbandResult], path: str) -> None:
        """Export d-band calculation results to CSV."""
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            header = ["Label", "Range", "d-band Center (eV)", "Width (eV)", "Filling%"]
            for o in d_orb_names:
                header.append(f"{o} Wt%")
            for o in d_orb_names:
                header.append(f"{o} Center(eV)")
            w.writerow(header)
            for rd in results_data:
                row = [
                    rd.label, rd.range_name,
                    f"{rd.center:.4f}" if np.isfinite(rd.center) else "NaN",
                    f"{rd.width:.4f}" if np.isfinite(rd.width) else "NaN",
                    f"{rd.filling:.1f}" if np.isfinite(rd.filling) else "NaN",
                ]
                if rd.is_aggregate_d:
                    # LORBIT=10 does not contain m-resolved components.
                    # Blank fields are intentionally distinguishable from a
                    # physical zero and prevent downstream data fabrication.
                    row.extend([""] * len(d_orb_names))
                    row.extend([""] * len(d_orb_names))
                else:
                    for o in d_orb_names:
                        row.append(f"{rd.orb_weights.get(o, 0):.1f}%")
                    for o in d_orb_names:
                        c = rd.orb_centers.get(o, float('nan'))
                        row.append(f"{c:.4f}" if np.isfinite(c) else "NaN")
                w.writerow(row)

    @staticmethod
    def export_hybridization_csv(
        e1, rho1, orbs1, label1,
        e2, rho2, orbs2, label2,
        path: str,
    ) -> None:
        """Export hybridization analysis data to CSV."""
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            header = ["Energy (eV)"]
            for o in orbs1:
                header.append(f"{label1}_{o}")
            for o in orbs2:
                header.append(f"{label2}_{o}")
            w.writerow(header)

            n = max(len(e1), len(e2))
            for i in range(n):
                row = []
                if i < len(e1):
                    row.append(f"{e1[i]:.6f}")
                else:
                    row.append("")
                for o in orbs1:
                    # Align missing orbitals to the energy grid length so the
                    # CSV has consistent columns (pandas-readable, no ragged).
                    arr = rho1.get(o, np.zeros_like(e1))
                    row.append(f"{arr[i]:.6f}" if i < len(arr) else "")
                for o in orbs2:
                    arr = rho2.get(o, np.zeros_like(e2))
                    row.append(f"{arr[i]:.6f}" if i < len(arr) else "")
                w.writerow(row)

    @staticmethod
    def save_figure(fig, path: str, dpi: int = 300) -> None:
        """Save a matplotlib Figure to file (PNG/PDF/SVG)."""
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
