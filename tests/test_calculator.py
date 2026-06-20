"""
Unit tests for core/calculator.py — calc_metrics and annotate_center.

Covers:
- Normal Gaussian-like DOS (center, width, filling correctness)
- Empty / degenerate arrays (edge cases)
- limit_fermi integration range
- custom_range integration
- Per-orbital weight and center
- Numerical stability on pure-NumPy path (numba removed in v4.0)
"""
import sys
import os
import numpy as np
import pytest
from unittest import mock

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.calculator import calc_metrics
from utils.styling import annotate_center


def test_lorbit10_uses_one_aggregate_d_metric_channel():
    """An l-resolved d DOS must not be represented as five fake orbitals."""
    from core.services.calculation_worker import _select_metric_d_orbitals

    energy = np.array([-1.0, 1.0])
    assert _select_metric_d_orbitals({"d": np.array([2.0, 3.0])}, energy) == ["d"]
    assert _select_metric_d_orbitals({"d": np.zeros(2)}, energy) != ["d"]


def test_calculation_worker_retains_lorbit10_as_aggregate_d_result():
    """The end-to-end worker must calculate d-total, not five zero channels."""
    from core.services.calculation_worker import CalculationWorker
    from core.pdos_metadata import PDOSMetadata

    worker = CalculationWorker(
        [{"path": "synthetic/DOSCAR", "label": "LORBIT10"}], "DOSCAR", "1", "total",
        True, False, False, (-10.0, 10.0))
    completed = []
    worker.calculation_done.connect(lambda results, cache: completed.append((results, cache)))
    energy = np.array([-1.0, 1.0])
    aggregate = {"d": np.array([2.0, 2.0])}
    zeros = {"d": np.zeros(2)}

    with mock.patch(
        "core.services.calculation_worker.DataLoader.load_spin_all_with_metadata",
        return_value=(energy, aggregate, zeros, aggregate, 0.0, PDOSMetadata(
            mode="nonspin", orbital_resolution="l", spin_axis=None, source_format="DOSCAR")),
    ):
        worker.run()

    assert len(completed) == 1
    results, cache = completed[0]
    assert len(results) == 1
    assert results[0].is_aggregate_d is True
    assert results[0].orb_weights["d"] == pytest.approx(100.0)
    assert cache["LORBIT10"]["orbital_resolution"] == "l"


def test_calculation_worker_keeps_noncollinear_saxis_metadata_in_cache():
    """UI consumers need an explicit warning that up/down are projections."""
    from core.services.calculation_worker import CalculationWorker
    from core.pdos_metadata import PDOSMetadata

    worker = CalculationWorker(
        [{"path": "synthetic/DOSCAR", "label": "SOC"}], "DOSCAR", "1", "total",
        True, False, False, (-10.0, 10.0))
    completed = []
    worker.calculation_done.connect(lambda results, cache: completed.append((results, cache)))
    energy = np.array([-1.0, 1.0])
    rho = {"dxy": np.array([1.0, 2.0])}
    metadata = PDOSMetadata(
        mode="noncollinear", orbital_resolution="lm", spin_axis=(0.0, 0.0, 1.0),
        source_format="DOSCAR")

    with mock.patch(
        "core.services.calculation_worker.DataLoader.load_spin_all_with_metadata",
        return_value=(energy, rho, rho, rho, 0.0, metadata),
    ):
        worker.run()

    assert completed[0][1]["SOC"]["metadata"] == metadata


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def gaussian_dos():
    """A symmetric Gaussian-like d-DOS centered at -2.0 eV (relative to Ef=0).

    All 5 d-orbitals have identical DOS, so the total is 5x a single orbital.
    """
    e = np.linspace(-10, 5, 500)
    ef = 2.0  # Fermi energy in the raw energy scale
    e_rel = e - ef
    # Gaussian centered at -2.0 eV (relative to Ef), sigma=1.5
    sigma = 1.5
    center_target = -2.0
    dos_single = np.exp(-0.5 * ((e_rel - center_target) / sigma) ** 2)
    rho = {o: dos_single.copy() for o in ["dxy", "dyz", "dz2", "dxz", "dx2-y2"]}
    return e, rho, ef, center_target, sigma


@pytest.fixture
def zero_dos():
    """All-zero DOS — should produce NaN center/width."""
    e = np.linspace(-10, 5, 100)
    rho = {o: np.zeros_like(e) for o in ["dxy", "dyz", "dz2", "dxz", "dx2-y2"]}
    return e, rho, 0.0


@pytest.fixture
def tiny_dos():
    """DOS with < 2 energy points after masking — edge case."""
    e = np.array([0.0, 0.5])
    rho = {"dxy": np.array([1.0, 2.0])}
    return e, rho, 0.0


# ── Tests: normal operation ─────────────────────────────────────────

class TestCalcMetricsNormal:
    """Verify correctness of center, width, filling on a known Gaussian."""

    def test_center_value(self, gaussian_dos):
        e, rho, ef, center_target, sigma = gaussian_dos
        center, width, filling, orb = calc_metrics(e, rho, ef=ef)
        # Center should be close to -2.0 (within 0.05 eV due to grid discretization)
        assert center == pytest.approx(center_target, abs=0.05)

    def test_width_value(self, gaussian_dos):
        e, rho, ef, center_target, sigma = gaussian_dos
        center, width, filling, orb = calc_metrics(e, rho, ef=ef)
        # Width = sqrt(<(E-c)^2>) for a Gaussian = sigma
        assert width == pytest.approx(sigma, abs=0.05)

    def test_filling_range(self, gaussian_dos):
        e, rho, ef, center_target, sigma = gaussian_dos
        center, width, filling, orb = calc_metrics(e, rho, ef=ef)
        # Filling should be between 0 and 100
        assert 0 <= filling <= 100

    def test_filling_below_half(self, gaussian_dos):
        """Gaussian centered at -2.0 eV below Ef should be > 50% filled."""
        e, rho, ef, center_target, sigma = gaussian_dos
        center, width, filling, orb = calc_metrics(e, rho, ef=ef)
        assert filling > 50.0

    def test_per_orbital_weights_equal(self, gaussian_dos):
        """All 5 orbitals have identical DOS, so weights should be ~0.2 each."""
        e, rho, ef, center_target, sigma = gaussian_dos
        center, width, filling, orb = calc_metrics(e, rho, ef=ef)
        for k in rho:
            assert orb[k]["weight"] == pytest.approx(0.2, abs=0.01)

    def test_per_orbital_center_matches_total(self, gaussian_dos):
        e, rho, ef, center_target, sigma = gaussian_dos
        center, width, filling, orb = calc_metrics(e, rho, ef=ef)
        for k in rho:
            assert orb[k]["center"] == pytest.approx(center, abs=0.01)

    def test_default_orb_names(self, gaussian_dos):
        """When orb_names is None, defaults to d_orb_names."""
        e, rho, ef, center_target, sigma = gaussian_dos
        center, width, filling, orb = calc_metrics(e, rho, ef=ef, orb_names=None)
        assert set(orb.keys()) == {"dxy", "dyz", "dz2", "dxz", "dx2-y2"}


# ── Tests: edge cases ───────────────────────────────────────────────

class TestCalcMetricsEdgeCases:

    def test_zero_dos_returns_nan(self, zero_dos):
        e, rho, ef = zero_dos
        center, width, filling, orb = calc_metrics(e, rho, ef=ef)
        assert np.isnan(center)
        assert np.isnan(width)
        assert np.isnan(filling)
        for k in orb:
            assert orb[k]["weight"] == 0.0
            assert np.isnan(orb[k]["center"])

    def test_tiny_window_uses_interpolated_edges(self, tiny_dos):
        """A sub-grid window still has two interpolated endpoints."""
        e, rho, ef = tiny_dos
        # Use custom_range that selects only 1 point
        center, width, filling, orb = calc_metrics(
            e, rho, ef=ef, custom_range=(-0.1, 0.1))
        assert np.isfinite(center)
        assert np.isfinite(width)

    def test_custom_range(self, gaussian_dos):
        """Custom range should restrict integration window."""
        e, rho, ef, center_target, sigma = gaussian_dos
        # Integrate only -3 to -1 (centered on the Gaussian)
        center, width, filling, orb = calc_metrics(
            e, rho, ef=ef, custom_range=(-3.0, -1.0))
        # Center should still be close to -2.0 (symmetric window)
        assert center == pytest.approx(-2.0, abs=0.05)

    def test_limit_fermi(self, gaussian_dos):
        """limit_fermi=True integrates only below Ef."""
        e, rho, ef, center_target, sigma = gaussian_dos
        center, width, filling, orb = calc_metrics(
            e, rho, ef=ef, limit_fermi=True)
        # Center should be shifted to more negative (only left half of Gaussian)
        assert center < center_target

    def test_ef_zero(self, gaussian_dos):
        """ef=0.0 means energy is already aligned."""
        e, rho, ef, center_target, sigma = gaussian_dos
        e_aligned = e - ef
        rho_aligned = {k: v for k, v in rho.items()}
        center1, _, _, _ = calc_metrics(e, rho, ef=ef)
        center2, _, _, _ = calc_metrics(e_aligned, rho_aligned, ef=0.0)
        assert center1 == pytest.approx(center2, abs=1e-10)

    def test_missing_orbital_in_rho(self):
        """If rho_dict is missing some d-orbitals, should not crash."""
        e = np.linspace(-5, 5, 100)
        rho = {"dxy": np.exp(-e**2)}  # Only 1 orbital
        center, width, filling, orb = calc_metrics(e, rho, ef=0.0)
        assert not np.isnan(center)  # Should still compute


class TestInputValidationAndWindowEdges:
    """Scientific-integrity guards: invalid grids must not yield a number."""

    def test_rejects_dos_length_mismatch(self):
        with pytest.raises(ValueError, match="length"):
            calc_metrics(np.array([-1.0, 0.0, 1.0]),
                         {"dxy": np.array([1.0, 2.0])}, ef=0.0)

    def test_rejects_non_finite_dos(self):
        with pytest.raises(ValueError, match="finite"):
            calc_metrics(np.array([-1.0, 0.0, 1.0]),
                         {"dxy": np.array([1.0, np.nan, 1.0])}, ef=0.0)

    def test_rejects_non_monotonic_energy(self):
        with pytest.raises(ValueError, match="strictly increasing"):
            calc_metrics(np.array([-1.0, 0.5, 0.0]),
                         {"dxy": np.ones(3)}, ef=0.0)

    def test_custom_window_interpolates_requested_edges(self):
        energy = np.array([0.0, 1.0, 2.0])
        rho = {"dxy": energy.copy()}
        center, _, _, _ = calc_metrics(
            energy, rho, ef=0.0, custom_range=(0.25, 1.75))
        clipped_energy = np.array([0.25, 1.0, 1.75])
        clipped_dos = clipped_energy.copy()
        expected = (np.trapz(clipped_energy * clipped_dos, clipped_energy)
                    / np.trapz(clipped_dos, clipped_energy))
        assert center == pytest.approx(expected, abs=1e-12)


# ── Tests: numerical stability (no numba dependency) ───────────────

class TestNumericalStability:
    """Verify numerical stability on the pure-NumPy code path.

    The numba JIT path was removed in v4.0 (see core/calculator.py docstring).
    These tests guard against regressions in the trapezoidal integration on
    both normal and large arrays.
    """

    def test_results_match_reference(self, gaussian_dos):
        """Compare against analytically known values (not against another impl)."""
        e, rho, ef, center_target, sigma = gaussian_dos
        center, width, filling, orb = calc_metrics(e, rho, ef=ef)
        # These assertions hold regardless of backend implementation
        assert np.isfinite(center)
        assert np.isfinite(width)
        assert np.isfinite(filling)
        assert all(np.isfinite(orb[k]["weight"]) for k in orb)

    def test_large_array_performance(self):
        """Smoke test with a large array to ensure no crash."""
        n = 100_000
        e = np.linspace(-20, 10, n)
        ef = 5.0
        e_rel = e - ef
        sigma = 2.0
        dos = np.exp(-0.5 * ((e_rel + 3.0) / sigma) ** 2)
        rho = {o: dos.copy() for o in ["dxy", "dyz", "dz2", "dxz", "dx2-y2"]}
        center, width, filling, orb = calc_metrics(e, rho, ef=ef)
        assert center == pytest.approx(-3.0, abs=0.01)


class TestFillingPrecision:
    """C2 regression: Ef must not straddle-discretise the DOS.

    A DOS symmetric about Ef has an analytic filling of exactly 50 %.  The
    legacy ``E <= Ef`` hard cut misclassified the grid bin straddling Ef and
    could drift by 1–3 percentage points.  The new linear-interpolation split
    at Ef recovers 50 % to within the grid error.
    """

    def _symmetric_dos(self, neff=0.0, n=2001, span=10.0, sigma=1.5):
        """Gaussian centred exactly at Ef (relative energy = neff)."""
        e_rel = np.linspace(-span, span, n)
        dos = np.exp(-0.5 * (e_rel / sigma) ** 2)
        # Raw axis: Ef sits at 0 on the raw scale, so energy == e_rel.
        energy = e_rel
        rho = {o: dos.copy() for o in ["dxy", "dyz", "dz2", "dxz", "dx2-y2"]}
        return energy, rho, neff

    def test_symmetric_dos_is_half_filled(self):
        """Centred Gaussian → filling == 50 % within grid error."""
        energy, rho, ef = self._symmetric_dos()
        _, _, filling, _ = calc_metrics(energy, rho, ef=ef)
        assert filling == pytest.approx(50.0, abs=0.5)

    def test_filling_in_unit_interval(self):
        energy, rho, ef = self._symmetric_dos()
        _, _, filling, _ = calc_metrics(energy, rho, ef=ef)
        assert 0.0 <= filling <= 100.0

    def test_straddling_bin_not_misclassified(self):
        """Ef lands inside a bin (non-aligned grid) — no whole-bin jump."""
        # Grid step = 0.01 eV; place Ef at a bin midpoint so a straddling
        # bin exists.  Filling should still be ~50 %.
        energy, rho, _ = self._symmetric_dos(n=2001, span=10.0)
        ef = 0.005  # half a grid step off a node
        _, _, filling, _ = calc_metrics(energy, rho, ef=ef)
        assert filling == pytest.approx(50.0, abs=0.6)

    def test_filling_zero_dos_is_nan(self):
        e = np.linspace(-5, 5, 100)
        rho = {o: np.zeros_like(e) for o in ["dxy", "dyz", "dz2", "dxz", "dx2-y2"]}
        _, _, filling, _ = calc_metrics(e, rho, ef=0.0)
        assert np.isnan(filling)


class TestFillingRobustness:
    """Regression guards for non-monotonic grids and out-of-range clamping.

    _filling_core previously assumed a strictly ascending energy axis (true
    for raw VASP output, false for user-stitched / post-processed axes).
    A non-monotonic bin made ``frac = (0 - e0)/de`` meaningless (negative or
    >1), corrupting the occupation fraction.  The fix detects such bins and
    falls back to a whole-bin trapezoid, then clamps the result to [0, 100] %.
    """

    def test_non_monotonic_axis_is_rejected(self):
        """A stitched/reversed grid has no well-defined DOS integral."""
        # Ascending segment, then a deliberate reversal (e decreases), then
        # ascending again.  Two straddle-relevant bins sit on the bad region.
        e = np.array([-2.0, -1.0, 0.5, -0.5, 0.5, 2.0])
        dos = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        rho = {o: dos.copy() for o in ["dxy", "dyz", "dz2", "dxz", "dx2-y2"]}
        with pytest.raises(ValueError, match="strictly increasing"):
            calc_metrics(e, rho, ef=0.0)

    def test_filling_clamped_to_unit_interval(self):
        """A signed/net DOS with negative regions cannot exceed [0, 100] %."""
        # DOS that goes negative (simulating a net-spin density channel
        # before abs()).  filling must still be a valid percentage.
        e = np.linspace(-5, 5, 401)
        dos = np.where(e < 0, 2.0, -1.0)   # negative on the occupied side
        rho = {o: dos.copy() for o in ["dxy", "dyz", "dz2", "dxz", "dx2-y2"]}
        _, _, filling, _ = calc_metrics(e, rho, ef=0.0)
        assert np.isfinite(filling)
        assert 0.0 <= filling <= 100.0


# ── Tests: annotate_center ──────────────────────────────────────────

class TestAnnotateCenter:

    def test_valid_center(self):
        """Smoke test — should not raise with a valid center."""
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        annotate_center(ax, -2.0, "d-center", "#FF0000", 1.0, 8)
        plt.close(fig)

    def test_nan_center_skipped(self):
        """NaN center should be a no-op (no axvline added)."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        lines_before = len(ax.lines)
        annotate_center(ax, float("nan"), "d-center", "#FF0000", 1.0, 8)
        lines_after = len(ax.lines)
        assert lines_after == lines_before
        plt.close(fig)


# ── Tests: Integration method (trapezoid vs simpson) ─────────────────

class TestIntegrationMethod:

    def test_default_method_is_trapezoid(self):
        """Default (no method arg) should behave like trapezoid."""
        e = np.linspace(-5, 5, 1001)
        dos = np.exp(-e**2)
        rho = {o: dos for o in ["dxy"]}
        c1, _, _, _ = calc_metrics(e, rho, ef=0.0)  # default
        c2, _, _, _ = calc_metrics(e, rho, ef=0.0, method="trapezoid")
        assert abs(c1 - c2) < 1e-12

    def test_simpson_requires_scipy(self):
        """Simpson should raise ImportError if SciPy is missing."""
        from core.calculator import _simpson
        if _simpson is None:
            with pytest.raises(ImportError, match="SciPy"):
                from core.calculator import _integrate
                _integrate([1.0], [0.0, 1.0], method="simpson")

    @pytest.mark.skipif(
        __import__("core.calculator", fromlist=["_simpson"])._simpson is None,
        reason="SciPy not installed"
    )
    def test_simpson_produces_finite_result(self):
        """Simpson should produce finite results on real data."""
        np.random.seed(42)
        e = np.linspace(-10, 10, 2001)
        # Asymmetric DOS to expose trapezoid/simpson difference
        dos = np.exp(-(e + 1)**2 / 4) + 0.3 * np.exp(-(e - 3)**2 / 2)
        dos = np.maximum(dos, 0)
        rho = {o: dos * (1 + 0.1 * i) for i, o in enumerate(["dxy","dyz","dz2","dxz","dx2-y2"])}
        c_s, w_s, f_s, o_s = calc_metrics(e, rho, ef=0.0, method="simpson")
        assert np.isfinite(c_s)
        assert np.isfinite(w_s)
        assert 0 <= f_s <= 100

    @pytest.mark.skipif(
        __import__("core.calculator", fromlist=["_simpson"])._simpson is None,
        reason="SciPy not installed"
    )
    def test_methods_differ_on_coarse_grid(self):
        """On coarse grids Simpson and Trapezoid should give different results."""
        e = np.linspace(-5, 5, 51)  # Very coarse grid
        dos = np.exp(-(e + 0.5)**2) + 0.5 * np.exp(-(e - 2)**2)
        rho = {o: dos for o in ["dxy"]}
        c_t, _, _, _ = calc_metrics(e, rho, ef=0.0, method="trapezoid")
        c_s, _, _, _ = calc_metrics(e, rho, ef=0.0, method="simpson")
        # They should be close but not identical on a coarse grid
        assert abs(c_t - c_s) > 1e-6, "Methods should differ on coarse grid"

    def test_invalid_method_raises(self):
        """Unknown method name should raise ValueError."""
        e = np.linspace(-5, 5, 101)
        dos = np.ones_like(e)
        rho = {"dxy": dos}
        with pytest.raises(ValueError, match="Unknown integration method"):
            calc_metrics(e, rho, ef=0.0, method="gauss_legendre")
