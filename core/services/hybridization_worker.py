"""
Background hybridization analysis worker — parses two fragments async.

Prevents UI freezing when parsing large vasprun.xml files (100MB+).
Uses a shared cache to avoid re-parsing the same file on theme/range changes.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QThread, Signal

from core.loader import DataLoader
from core.exceptions import DbandError, FileTypeError
from core.parsers.common import _detect_has_spin


class HybridizationWorker(QThread):
    """Background worker: parse two fragments without blocking the UI thread.

    Signals:
        result_ready(object, object, object)   — (frag1_data, frag2_data, distance_results)
        error_occurred(str, str)       — (error_type, message)
    """
    result_ready = Signal(object, object, object)
    error_occurred = Signal(str, str)

    def __init__(
        self,
        frag1_params: Tuple,
        frag2_params: Tuple,
        geom_params: Optional[Tuple] = None,
        local_cache: Optional[Dict] = None,
        shared_cache: Optional[Dict] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.p1 = frag1_params
        self.p2 = frag2_params
        self.geom_params = geom_params
        self._local_cache = local_cache if local_cache is not None else {}
        self._shared_cache = shared_cache

    def run(self):
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as executor:
                future1 = executor.submit(self._parse_with_cache, self.p1)
                future2 = executor.submit(self._parse_with_cache, self.p2)
                data1 = future1.result()
                data2 = future2.result()
            
            distance_results = None
            if self.geom_params is not None:
                _, fp1, atoms1, _, _, _ = self.p1
                _, fp2, atoms2, _, _, _ = self.p2
                
                if len(self.geom_params) == 4:
                    cutoff, mode, b_atoms1, b_atoms2 = self.geom_params
                else:
                    cutoff, mode = self.geom_params
                    b_atoms1, b_atoms2 = atoms1, atoms2
                
                if fp1 and fp2 and fp1 == fp2 and fp1.lower().endswith(".xml"):
                    from core.parsers.vasprun import get_vasprun_distances
                    distance_results = get_vasprun_distances(fp1, b_atoms1, b_atoms2, cutoff, mode)

            self.result_ready.emit(data1, data2, distance_results)
        except (FileTypeError, DbandError) as e:
            self.error_occurred.emit(type(e).__name__, str(e))
        except ValueError as e:
            self.error_occurred.emit("ValueError", str(e))
        except Exception as e:
            self.error_occurred.emit("UnexpectedError", str(e))

    def _parse_with_cache(self, params: Tuple) -> Tuple:
        """Parse a fragment, using cache if available.

        Cache key: (filepath, mtime, atoms, spin, sorted_orbitals).

        ``mtime`` is included so that a file replaced in place (same path,
        new contents — e.g. a re-run VASP calculation overwriting the old
        vasprun.xml) invalidates the stale entry instead of returning the
        previous parse's DOS arrays.
        """
        label, fp, atoms, orbitals, spin, alias = params
        if not fp:
            raise ValueError("Please select a data source file.")
        if not orbitals:
            raise ValueError("Please select at least one orbital.")

        # Best-effort mtime: 0 if the file is gone (treat as uncached-via-mtime
        # but still keyed by the path, which is the strongest signal available).
        try:
            mtime = int(os.path.getmtime(fp))
        except OSError:
            mtime = 0

        cache_key = (fp, mtime, atoms, spin, tuple(sorted(orbitals)))

        # Check local cache first
        if cache_key in self._local_cache:
            e_aligned, r_up, r_dn, _old_orbs, _alias = self._local_cache[cache_key]
            # Use .get(o, zeros) fallback for consistency with the full-parse path;
            # silently skipping missing orbitals would diverge from the contract.
            r_up_new = ({o: r_up.get(o, np.zeros_like(e_aligned)) for o in orbitals}
                        if r_up else None)
            r_dn_new = ({o: r_dn.get(o, np.zeros_like(e_aligned)) for o in orbitals}
                        if r_dn else None)
            return (e_aligned, r_up_new, r_dn_new, orbitals, alias)

        # Check shared cache (AppState.parsed_cache) by label.
        # CRITICAL: the shared cache is keyed by *label*, which the user can
        # rename or reuse across different files.  Two files both labelled
        # "Pt(111)" would otherwise cross-contaminate.  Require the cached
        # entry's stored filepath to match the current fp; entries missing a
        # filepath field (older cache writes) are treated as unverified and
        # skipped, falling through to a correct full re-parse.
        if self._shared_cache is not None and label in self._shared_cache:
            entry = self._shared_cache[label]
            if entry.get("atoms") == atoms and entry.get("filepath") == fp:
                energy = entry["energy"]
                ef = entry["ef"]
                rho_up_full = entry["up"]
                rho_dn_full = entry["down"]
                has_spin = entry["has_spin"]
    
                e_aligned = energy - ef
                def filter_orbs(r):
                    return {o: r.get(o, np.zeros_like(e_aligned)) for o in orbitals}
    
                if spin == "up":
                    result = (e_aligned, filter_orbs(rho_up_full), None, orbitals, alias)
                elif spin == "down":
                    result = (e_aligned, None, filter_orbs(rho_dn_full), orbitals, alias)
                else:
                    if not has_spin:
                        result = (e_aligned, filter_orbs(rho_up_full), None, orbitals, alias)
                    else:
                        result = (e_aligned, filter_orbs(rho_up_full), filter_orbs(rho_dn_full), orbitals, alias)
    
                self._local_cache[cache_key] = result
                return result

        # Cache miss — full parse
        energy, rho_up, rho_dn, rho_total, ef = DataLoader.load_spin_all(fp, atoms, orbitals=orbitals)

        e_aligned = energy - ef
        def filter_orbs(r):
            return {o: r.get(o, np.zeros_like(e_aligned)) for o in orbitals}

        if spin == "up":
            result = (e_aligned, filter_orbs(rho_up), None, orbitals, alias)
        elif spin == "down":
            result = (e_aligned, None, filter_orbs(rho_dn), orbitals, alias)
        else:
            has_spin = _detect_has_spin(rho_dn)
            if not has_spin:
                result = (e_aligned, filter_orbs(rho_up), None, orbitals, alias)
            else:
                result = (e_aligned, filter_orbs(rho_up), filter_orbs(rho_dn), orbitals, alias)

        self._local_cache[cache_key] = result
        return result
