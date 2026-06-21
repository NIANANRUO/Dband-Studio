"""
Background calculation worker — parses files and computes d-band metrics.

Extracted from ui/main_window.py to separate business logic from UI.
Uses QThread to avoid blocking the main thread during file parsing.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QThread, Signal

from core.loader import DataLoader
from core.exceptions import (
    DbandError, AtomNotFoundError, MissingProjectedDOSError, FileTypeError,
)
from core.parsers import d_orb_names
from core.parsers.common import _detect_has_spin
from core.calculator import calc_metrics
from core.services.file_identity import file_fingerprint
from models.results import DbandResult


def _select_metric_d_orbitals(rho_total, energy):
    """Choose the physically available d resolution for the band moment."""
    aggregate = rho_total.get("d")
    if aggregate is not None:
        arr = np.asarray(aggregate, dtype=np.float64)
        if arr.shape == np.asarray(energy).shape and np.isfinite(arr).all() and np.any(arr != 0):
            return ["d"]
    return list(d_orb_names)


class CalculationWorker(QThread):
    """Background worker: parse files + compute metrics without blocking UI.

    Signals:
        progress(int, int)               — current, total
        file_done(str)                   — label
        file_error(str, str, str)        — label, error_type, message
        ef_warning(str)                  — label of file whose ef is assumed 0 (VASPKIT)
        calculation_done(list, dict)     — results_data, parsed_cache
    """
    progress = Signal(int, int)
    file_done = Signal(str)
    file_error = Signal(str, str, str)
    ef_warning = Signal(str)
    calculation_done = Signal(list, dict)

    def __init__(self, file_entries, chosen_type, atoms, spin,
                 do_all, do_fermi, do_custom, custom_range,
                 integration_method="trapezoid", parent=None):
        super().__init__(parent)
        self.file_entries = file_entries
        self.chosen_type = chosen_type
        self.atoms = atoms
        self.spin = spin
        self.do_all = do_all
        self.do_fermi = do_fermi
        self.do_custom = do_custom
        self.custom_range = custom_range
        self.integration_method = integration_method
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        results_data: list = []
        parsed_cache = {}
        total = len(self.file_entries)

        for i, entry in enumerate(self.file_entries):
            if self._cancelled:
                break
            self.progress.emit(i + 1, total)

            fp, label = entry["path"], entry["label"]
            file_atoms = entry.get("atoms", "").strip()
            current_atoms = file_atoms if file_atoms else self.atoms
            
            try:
                ftype = self.chosen_type
                if ftype == "Auto Detect":
                    ftype = DataLoader.detect(fp)

                # Only d-orbitals are needed for d-band metrics; requesting
                # just them avoids parsing/allocating 11 unused s/p/f arrays
                # (3× memory saving on large systems).
                requested_orbitals = [*d_orb_names, "d"]
                energy, rho_up, rho_dn, rho_total, ef, metadata = DataLoader.load_spin_all_with_metadata(
                    fp, current_atoms, orbitals=requested_orbitals)
                # VASPKIT PDOS files never embed the Fermi level (ef forced to 0).
                # Warn once per file so users know the energy axis is NOT aligned.
                if ftype == "VASPKIT PDOS":
                    self.ef_warning.emit(label)
                if self.spin == "up":
                    rho = rho_up
                elif self.spin == "down":
                    rho = rho_dn
                else:
                    rho = rho_total

                metric_orbitals = _select_metric_d_orbitals(rho_total, energy)
                orbital_resolution = "l" if metric_orbitals == ["d"] else "lm"
                rho_d = {o: rho.get(o, np.zeros_like(energy)) for o in metric_orbitals}
                total_check = sum(np.sum(np.abs(v)) for v in rho_d.values())
                if total_check == 0:
                    raise MissingProjectedDOSError(label, filepath=fp)

                # Detect spin-polarisation by checking whether any orbital
                # in the down channel carries non-zero DOS.
                is_spin = metadata.mode in {"collinear", "noncollinear"}

                # Cache — store RAW energy + ef (not pre-aligned).
                # ``filepath`` is recorded so HybridizationWorker can verify
                # that a shared_cache hit by *label* actually corresponds to
                # this file (labels are user-editable and can be reused).
                parsed_cache[label] = {
                    "atoms": current_atoms,
                    "filepath": fp,
                    "file_fingerprint": file_fingerprint(fp),
                    "energy": energy,
                    "ef": ef,
                    "up": rho_up,
                    "down": rho_dn,
                    "has_spin": is_spin,
                    "orbital_resolution": orbital_resolution,
                    "d_orbitals": metric_orbitals,
                    "metadata": metadata,
                }

                ranges = []
                if self.do_all:
                    ranges.append(("All", False, None))
                if self.do_fermi:
                    ranges.append(("< Ef", True, None))
                if self.do_custom:
                    ranges.append(
                        (f"[{self.custom_range[0]},{self.custom_range[1]}]",
                         False, self.custom_range))

                for rname, rlim, rcust in ranges:
                    center, width, filling, om = calc_metrics(
                        energy, rho_d, ef, orb_names=metric_orbitals,
                        limit_fermi=rlim, custom_range=rcust,
                        method=self.integration_method)

                    rd = DbandResult(
                        label=label,
                        range_name=rname,
                        center=center,
                        width=width,
                        filling=filling,
                        orb_weights={o: om[o]["weight"] * 100 for o in metric_orbitals},
                        orb_centers={o: om[o]["center"] for o in metric_orbitals},
                        orbital_resolution=orbital_resolution,
                    )
                    results_data.append(rd)

                self.file_done.emit(label)

            except (MissingProjectedDOSError, AtomNotFoundError, FileTypeError) as e:
                self.file_error.emit(label, type(e).__name__, str(e))
            except DbandError as e:
                self.file_error.emit(label, type(e).__name__, str(e))
            except Exception as e:
                self.file_error.emit(label, "UnexpectedError", str(e))

        self.calculation_done.emit(results_data, parsed_cache)
