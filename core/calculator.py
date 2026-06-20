"""
Numerical integration and band-center calculations (pure NumPy / SciPy).

Design notes
------------
Two integration methods are available, selected at call time via the
``method`` parameter:

* **"trapezoid"** (default) — ``numpy.trapezoid`` (or ``np.trapz`` on
  NumPy 1.x).  First-order accurate, O(ΔE) per bin.  Fast and requires
  only NumPy.  This was the original method used in all prior versions.

* **"simpson"** — ``scipy.integrate.simpson``.  Third-order accurate,
  O(ΔE³) per bin.  Matches VASPKit task-287 output (which uses Simpson)
  to within <1 % on typical VASP DOS grids.  Requires SciPy.

The previous Numba JIT path was removed: for DOS-scale arrays (typically
10³–10⁵ points) vectorised NumPy is already sub-millisecond, while Numba
added cross-version nopy-mode fragility, a multi-second first-call cost,
and PyInstaller packaging conflicts.

Definitions (kept consistent with the Hammer–Nørskov d-band framework):
    center  = ∫ E·ρ(E)dE / ∫ ρ(E)dE                  (first moment)
    width   = sqrt( ∫ (E−center)²·ρ(E)dE / ∫ ρ(E)dE )   (standard deviation)
    filling = 100 · ∫_{E≤Ef} ρ(E)dE / ∫ ρ(E)dE        (occupation fraction)

The ``width`` above is the **second-moment standard deviation**.  It is NOT
the FWHM and may differ from VASPKIT task-11x "width" output.  When
``limit_fermi`` or ``custom_range`` is set, center/width/weights are computed
inside that window only; ``filling`` is always over the full energy axis.

Filling precision
-----------------
The Fermi level rarely lands exactly on an energy grid point.  The previous
implementation used a hard ``E <= Ef`` cut, which either fully included or
fully excluded the straddling bin — a systematic O(ΔE) error that can shift
filling by 1–3 percentage points on coarse VASP grids.  Here the straddling
bin is split by linear interpolation to Ef, eliminating the discontinuity.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.parsers.constants import d_orb_names

_logger = logging.getLogger("dband.calculator")

# ---------------------------------------------------------------------------
# Integration backends
# ---------------------------------------------------------------------------
# numpy-version-safe trapezoidal alias.  numpy>=2.0 removed np.trapz;
# resolve once at import time and reuse everywhere (works on numpy 1.x too).
_trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)
if _trapz is None:  # pragma: no cover
    raise ImportError(
        "NumPy trapezoidal integration unavailable; requires numpy>=1.10"
    )

# Simpson's rule via SciPy (optional — only needed when method="simpson").
_simpson = None
_SIMPSON_IMPORT_ERROR: Optional[str] = None
try:
    from scipy.integrate import simpson as _simpson  # type: ignore[no-redef]
except Exception as exc:
    _SIMPSON_IMPORT_ERROR = str(exc)

#: Supported integration methods.
VALID_METHODS = ("trapezoid", "simpson")


def _validate_metrics_inputs(
    energy: np.ndarray,
    rho_dict: Dict[str, np.ndarray],
    orb_names: List[str],
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Return validated float64 inputs for a scientific DOS moment.

    A malformed energy grid or a partially read PDOS must fail before any
    numerical result is constructed.  Returning a plausible value for such
    input is materially worse than rejecting the file.
    """
    energy = np.asarray(energy, dtype=np.float64)
    if energy.ndim != 1:
        raise ValueError("Energy axis must be one-dimensional.")
    if not np.isfinite(energy).all():
        raise ValueError("Energy axis must contain only finite values.")
    if energy.size >= 2 and not np.all(np.diff(energy) > 0.0):
        raise ValueError("Energy axis must be strictly increasing.")

    arrays: Dict[str, np.ndarray] = {}
    for name in orb_names:
        if name not in rho_dict:
            continue
        arr = np.asarray(rho_dict[name], dtype=np.float64)
        if arr.ndim != 1 or arr.shape[0] != energy.shape[0]:
            raise ValueError(
                f"DOS array '{name}' length must match the energy axis.")
        if not np.isfinite(arr).all():
            raise ValueError(
                f"DOS array '{name}' must contain only finite values.")
        arrays[name] = arr
    return energy, arrays


def _clip_window(
    energy: np.ndarray,
    arrays: Dict[str, np.ndarray],
    lower: float,
    upper: float,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Restrict DOS arrays to a closed window, interpolating both edges."""
    lower = max(float(lower), float(energy[0]))
    upper = min(float(upper), float(energy[-1]))
    if lower >= upper:
        return np.empty(0, dtype=np.float64), {
            key: np.empty(0, dtype=np.float64) for key in arrays
        }

    interior = (energy > lower) & (energy < upper)
    clipped_energy = np.concatenate(([lower], energy[interior], [upper]))
    clipped = {
        key: np.concatenate((
            [np.interp(lower, energy, values)],
            values[interior],
            [np.interp(upper, energy, values)],
        ))
        for key, values in arrays.items()
    }
    return clipped_energy, clipped


def _integrate(y, x, *, axis=None, method="trapezoid"):
    """Dispatch to the selected numerical integration backend.

    Parameters
    ----------
    y : array-like   Integrand.
    x : array-like   Independent variable (energy axis).
    axis : int | None   Axis along which to integrate (for multi-D *y*).
    method : ``"trapezoid"`` | ``"simpson"``
        Integration rule.  ``"trapezoid"`` uses NumPy only (always
        available); ``"simpson"`` requires **SciPy**.

    Returns
    -------
    float | ndarray
    """
    if method not in VALID_METHODS:
        raise ValueError(
            f"Unknown integration method '{method}'. "
            f"Must be one of {VALID_METHODS}."
        )
    if method == "simpson":
        if _simpson is None:
            raise ImportError(
                f"Simpson's rule requires SciPy ({_SIMPSON_IMPORT_ERROR}). "
                "Install with: pip install scipy"
            )
        # scipy.integrate.simpson does NOT accept axis=None; must omit
        # the kwarg for 1-D arrays or pass an explicit int for N-D.
        if axis is not None:
            return _simpson(y, x, axis=axis)
        return _simpson(y, x)
    # Default: trapezoidal rule
    if axis is not None:
        return _trapz(y, x, axis=axis)
    return _trapz(y, x)


def _integrate_core(
    ec: np.ndarray,
    total: np.ndarray,
    *,
    method="trapezoid",
) -> Tuple[float, float, float]:
    """Center, width, norm from an energy axis and total DOS.

    Returns ``(center, width, norm)``.  A zero or non-finite norm yields
    ``(nan, nan, 0.0)`` so the caller can short-circuit.
    """
    ec = np.asarray(ec, dtype=np.float64)
    total = np.asarray(total, dtype=np.float64)
    norm = _integrate(total, ec, method=method)
    if norm == 0.0 or not np.isfinite(norm):
        return np.nan, np.nan, 0.0
    center = _integrate(ec * total, ec, method=method) / norm
    diff = ec - center
    var = _integrate(diff * diff * total, ec, method=method) / norm
    var = max(var, 0.0)  # guard tiny negative from round-off
    width = np.sqrt(var)
    return float(center), float(width), float(norm)


def _filling_core(e_full: np.ndarray, total_full: np.ndarray, *,
                  method="trapezoid") -> float:
    """Occupation percentage below Ef (e_full is energy − Ef, so Ef == 0).

    Bins straddling Ef (``e0 <= 0 < e1``) are split by linear interpolation
    to e=0 instead of being wholly included/excluded.  VASP DOS grids are
    monotonically ascending; if a non-monotonic axis is detected (e.g. a
    user-stitched or post-processed grid), the straddling-bin interpolation
    is skipped for those bins (it would produce a meaningless ``frac``) and
    a whole-bin trapezoid is used instead, with a WARNING.
    """
    e_full = np.asarray(e_full, dtype=np.float64)
    total_full = np.asarray(total_full, dtype=np.float64)
    if e_full.shape[0] < 2:
        return np.nan

    norm = _integrate(total_full, e_full, method=method)
    if norm == 0.0 or not np.isfinite(norm):
        return np.nan

    e0 = e_full[:-1]
    e1 = e_full[1:]
    t0 = total_full[:-1]
    t1 = total_full[1:]
    de = e1 - e0

    # Non-monotonic bins invalidate the linear-interpolation fraction
    # (0 - e0)/de, which can go negative or exceed 1.  Detect once and fall
    # back to a whole-bin trapezoid for the straddle on those bins.
    non_mono = de <= 0.0
    if np.any(non_mono):
        _logger.warning(
            "Energy axis is non-monotonic at %d / %d bins; falling back to "
            "whole-bin filling (O(ΔE) accuracy) for those bins.",
            int(np.sum(non_mono)), de.size)

    # Whole bins strictly below Ef contribute their full trapezoid area.
    below = e1 <= 0.0
    # Bins that straddle Ef (e0 <= 0 < e1).  Interpolation is only valid on
    # monotonic bins; non-monotonic straddlers are handled via ``below``/whole.
    straddle_interp = (e0 <= 0.0) & (e1 > 0.0) & ~non_mono
    # Non-monotonic straddlers: treat as fully occupied (conservative; the
    # sign of de means the "below Ef" portion cannot be cleanly isolated).
    straddle_whole = (e0 <= 0.0) & (e1 > 0.0) & non_mono

    area = np.zeros_like(e0, dtype=np.float64)
    if np.any(below | straddle_whole):
        sel = below | straddle_whole
        area[sel] = (t0[sel] + t1[sel]) * de[sel] * 0.5
    if np.any(straddle_interp):
        # Fraction of the bin width lying below Ef.
        frac = (0.0 - e0[straddle_interp]) / de[straddle_interp]
        # DOS value at Ef by linear interpolation within the straddling bin.
        t_ef = t0[straddle_interp] + frac * (t1[straddle_interp] - t0[straddle_interp])
        area[straddle_interp] = (t0[straddle_interp] + t_ef) * (0.0 - e0[straddle_interp]) * 0.5

    occ = float(np.sum(area))
    # Clamp to the physical [0, 100] % range: round-off or a signed/net DOS
    # (where total_full carries negative regions) can push occ/norm slightly
    # outside the interval.
    return max(0.0, min(100.0, occ / norm * 100.0))


def _orbital_metrics_core(
    ec: np.ndarray,
    rho_arrays: np.ndarray,
    norm_total: float,
    *,
    method="trapezoid",
) -> Tuple[np.ndarray, np.ndarray]:
    """Per-orbital weight (relative share) and center.

    Args:
        ec: masked energy axis (1D)
        rho_arrays: 2D array (n_orbitals × n_points)
        norm_total: total normalisation from ``_integrate_core``
        method: integration method ("trapezoid" or "simpson")

    Returns:
        (weights, centers) — 1D arrays of length ``rho_arrays.shape[0]``.
        ``weights`` are the share of each orbital within ``ec`` (sum to 1
        when every orbital is non-negative).  ``centers`` are ``nan`` for
        orbitals with non-positive norm.
    """
    ec = np.asarray(ec, dtype=np.float64)
    rho_arrays = np.ascontiguousarray(rho_arrays, dtype=np.float64)
    n_orbs = rho_arrays.shape[0]

    # Per-orbital norms — vectorised over the orbital axis.
    onorms = _integrate(rho_arrays, ec, axis=1, method=method)
    if norm_total != 0.0 and np.isfinite(norm_total):
        weights = onorms / norm_total
    else:
        weights = np.zeros(n_orbs, dtype=np.float64)

    centers = np.full(n_orbs, np.nan, dtype=np.float64)
    valid = onorms > 0.0
    if np.any(valid):
        integrands = ec * rho_arrays[valid]          # (k, n_points)
        num = _integrate(integrands, ec, axis=1, method=method)  # (k,)
        centers[valid] = num / onorms[valid]
    return weights, centers


def calc_metrics(
    energy: np.ndarray,
    rho_dict: Dict[str, np.ndarray],
    ef: float = 0.0,
    orb_names: Optional[List[str]] = None,
    limit_fermi: bool = False,
    custom_range: Optional[Tuple[float, float]] = None,
    method: str = "trapezoid",
) -> Tuple[float, float, float, Dict[str, Dict[str, float]]]:
    """Calculate band center, width, filling and per-orbital metrics.

    Args:
        energy: raw energy axis (need not be aligned to Ef).
        rho_dict: ``{orbital_name: density_array}`` aligned with ``energy``.
        ef: Fermi energy; subtracted from ``energy`` before integration.
        orb_names: orbitals to analyse; defaults to ``d_orb_names``.
        limit_fermi: if True, integrate only below Ef.
        custom_range: ``(emin, emax)`` integration window (relative to Ef).
        method: integration method — ``"trapezoid"`` (default, NumPy only)
                or ``"simpson"`` (requires SciPy; matches VASPKit).

    Returns:
        ``(center, width, filling, orb_metrics)`` where ``orb_metrics`` is
        ``{orb: {"weight": float, "center": float}}``.  Degenerate inputs
        (fewer than 2 points, all-zero DOS) yield ``nan`` scalars and
        zero-weight orbitals.
    """
    if orb_names is None:
        orb_names = d_orb_names

    energy, validated_rho = _validate_metrics_inputs(energy, rho_dict, orb_names)
    if not np.isfinite(ef):
        raise ValueError("Fermi energy must be finite.")
    e = energy - ef

    if custom_range is not None:
        if custom_range[0] >= custom_range[1]:
            raise ValueError("Custom integration range must have emin < emax.")
        ec, rc = _clip_window(e, validated_rho, custom_range[0], custom_range[1])
    elif limit_fermi:
        ec, rc = _clip_window(e, validated_rho, e[0], 0.0)
    else:
        ec, rc = e, validated_rho

    empty = {k: {"weight": 0.0, "center": np.nan} for k in orb_names}
    if ec.shape[0] < 2:
        return np.nan, np.nan, np.nan, empty

    total = np.zeros_like(ec, dtype=np.float64)
    for k in orb_names:
        arr = rc.get(k)
        if arr is not None:
            total += arr

    # ── Center / width over the selected window ────────────────────────
    center, width, norm = _integrate_core(ec, total, method=method)
    if norm == 0.0 or np.isnan(norm):
        return np.nan, np.nan, np.nan, empty

    # ── Filling over the FULL axis (independent of window) ─────────────
    e_full = energy - ef
    total_full = np.zeros_like(e_full, dtype=np.float64)
    for k in orb_names:
        arr = validated_rho.get(k)
        if arr is not None:
            total_full += np.asarray(arr, dtype=np.float64)
    filling = _filling_core(e_full, total_full, method=method)

    # ── Per-orbital metrics over the selected window ───────────────────
    n_orbs = len(orb_names)
    rho_arrays = np.zeros((n_orbs, ec.shape[0]), dtype=np.float64)
    for i, k in enumerate(orb_names):
        arr = rc.get(k)
        if arr is not None:
            rho_arrays[i] = arr

    weights, centers = _orbital_metrics_core(ec, rho_arrays, norm, method=method)
    orb_metrics = {
        k: {"weight": float(weights[i]), "center": float(centers[i])}
        for i, k in enumerate(orb_names)
    }

    return float(center), float(width), float(filling), orb_metrics
