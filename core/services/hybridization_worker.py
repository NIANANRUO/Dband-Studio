"""
Background hybridization analysis worker — parses two fragments async.

Prevents UI freezing when parsing large vasprun.xml files (100MB+).
Uses a shared cache to avoid re-parsing the same file on theme/range changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QThread, Signal

from core.loader import DataLoader
from core.exceptions import DbandError, FileTypeError
from core.parsers.common import _detect_has_spin
from core.orbital_selection import (
    ResolvedOrbitalRequest, materialize_orbital_outputs,
    resolve_orbital_request,
)
from core.pdos_metadata import PDOSCapabilities
from core.services.file_identity import context_fingerprint, file_fingerprint
from core.pdos_metadata import PDOSInputContext


@dataclass(frozen=True)
class GeometryAnalysisResult:
    """Geometry output plus an honest explanation when it cannot be computed."""

    pairs: Optional[List[Tuple[str, str, float]]]
    diagnostic: Optional[str] = None


def geometry_input_diagnostic(filepath1: str, filepath2: str) -> Optional[str]:
    """Return why a shared vasprun geometry calculation is unavailable.

    Bond distances are only physically meaningful when both fragments refer to
    the same structure embedded in one vasprun.xml file.  The previous UI
    collapsed every rejection into "requires vasprun.xml", which hid the
    selected files and made scientific diagnosis impossible.
    """
    if not filepath1 or not filepath2:
        return "Bond lengths require a selected source file for both fragments."

    is_xml1 = filepath1.lower().endswith(".xml")
    is_xml2 = filepath2.lower().endswith(".xml")
    if not (is_xml1 and is_xml2):
        return (
            "Bond lengths require both fragments to use the same vasprun.xml; "
            f"selected: '{os.path.basename(filepath1)}' and "
            f"'{os.path.basename(filepath2)}'."
        )

    normalized1 = os.path.normcase(os.path.abspath(filepath1))
    normalized2 = os.path.normcase(os.path.abspath(filepath2))
    if normalized1 != normalized2:
        return (
            "Bond lengths require both fragments to use the same vasprun.xml; "
            f"selected: '{filepath1}' and '{filepath2}'."
        )
    return None


class HybridizationWorker(QThread):
    """Background worker: parse two fragments without blocking the UI thread.

    Signals:
        result_ready(object, object, object)   — (frag1_data, frag2_data, distance_results)
        error_occurred(str, str)       — (error_type, message)
    """
    result_ready = Signal(object, object, object)
    error_occurred = Signal(str, str)
    progress = Signal(str)

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
            self.progress.emit("Parsing selected fragment DOS data...")
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as executor:
                future1 = executor.submit(self._parse_with_cache, self.p1)
                future2 = executor.submit(self._parse_with_cache, self.p2)
                data1 = future1.result()
                data2 = future2.result()
            
            geometry_result = GeometryAnalysisResult(None)
            if self.geom_params is not None:
                _, fp1, atoms1, _, _, _ = self.p1[:6]
                _, fp2, atoms2, _, _, _ = self.p2[:6]
                
                if len(self.geom_params) == 4:
                    cutoff, mode, b_atoms1, b_atoms2 = self.geom_params
                else:
                    cutoff, mode = self.geom_params
                    b_atoms1, b_atoms2 = atoms1, atoms2
                
                diagnostic = geometry_input_diagnostic(fp1, fp2)
                if diagnostic is None:
                    self.progress.emit("Calculating bond lengths from vasprun.xml...")
                    from core.parsers.vasprun import get_vasprun_distances
                    pairs = get_vasprun_distances(fp1, b_atoms1, b_atoms2, cutoff, mode)
                    geometry_result = GeometryAnalysisResult(pairs)
                else:
                    geometry_result = GeometryAnalysisResult(None, diagnostic)

            self.progress.emit("Rendering hybridization plot...")
            self.result_ready.emit(data1, data2, geometry_result)
        except (FileTypeError, DbandError) as e:
            self.error_occurred.emit(type(e).__name__, str(e))
        except ValueError as e:
            self.error_occurred.emit("ValueError", str(e))
        except Exception as e:
            self.error_occurred.emit("UnexpectedError", str(e))

    def _parse_with_cache(self, params: Tuple) -> Tuple:
        """Parse a fragment, using cache if available.

        Cache key: (filepath, fingerprint, atoms, spin, sorted_orbitals).

        ``mtime`` is included so that a file replaced in place (same path,
        new contents — e.g. a re-run VASP calculation overwriting the old
        vasprun.xml) invalidates the stale entry instead of returning the
        previous parse's DOS arrays.
        """
        label, fp, atoms, orbitals, spin, alias = params[:6]
        explicit_context = params[6] if len(params) > 6 else None
        if not fp:
            raise ValueError("Please select a data source file.")
        if not orbitals:
            raise ValueError("Please select at least one orbital.")

        source = explicit_context or fp
        capabilities = DataLoader.inspect(source)
        if isinstance(capabilities, PDOSCapabilities):
            resolved = resolve_orbital_request(orbitals, capabilities)
            capability_key = (
                capabilities.spin_mode, capabilities.orbital_resolution,
                capabilities.available_orbitals)
        else:
            # Compatibility for third-party loaders that do not yet expose an
            # inspector. Missing channels are still rejected below.
            resolved = ResolvedOrbitalRequest(
                tuple(orbitals), {orbital: (orbital,) for orbital in orbitals})
            capability_key = ("unknown", "unknown", ())

        fingerprint = file_fingerprint(fp)
        authorized_fingerprint = (
            context_fingerprint(explicit_context)
            if isinstance(explicit_context, PDOSInputContext) else None)
        cache_key = (
            fp, fingerprint, authorized_fingerprint, atoms, spin,
            tuple(sorted(orbitals)), capability_key)

        # Check local cache first
        if cache_key in self._local_cache:
            cached = self._local_cache[cache_key]
            # Alias is presentation metadata, not part of the parsed DOS cache
            # identity.  Always attach the current value so a renamed fragment
            # cannot inherit the label from an earlier calculation.
            return (*cached[:4], alias)

        # Check shared cache (AppState.parsed_cache) by label.
        # CRITICAL: the shared cache is keyed by *label*, which the user can
        # rename or reuse across different files.  Two files both labelled
        # "Pt(111)" would otherwise cross-contaminate.  Require the cached
        # entry's stored filepath to match the current fp; entries missing a
        # filepath field (older cache writes) are treated as unverified and
        # skipped, falling through to a correct full re-parse.
        if self._shared_cache is not None and label in self._shared_cache:
            entry = self._shared_cache[label]
            if (entry.get("atoms") == atoms
                    and entry.get("filepath") == fp
                    and entry.get("file_fingerprint") == fingerprint
                    and (authorized_fingerprint is None or
                         entry.get("context_fingerprint") == authorized_fingerprint)):
                energy = entry["energy"]
                ef = entry["ef"]
                rho_up_full = entry["up"]
                rho_dn_full = entry["down"]
                has_spin = entry["has_spin"]
                required = set(resolved.parser_orbitals)
                cache_has_required = required <= set(rho_up_full)
                if not cache_has_required:
                    entry = None
                else:
                    e_aligned = energy - ef
                    def filter_orbs(r):
                        return materialize_orbital_outputs(r, resolved)

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
        energy, rho_up, rho_dn, rho_total, ef = DataLoader.load_spin_all(
            source, atoms, orbitals=list(resolved.parser_orbitals))

        e_aligned = energy - ef
        def filter_orbs(r):
            return materialize_orbital_outputs(r, resolved)

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
