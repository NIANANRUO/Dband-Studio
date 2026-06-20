"""
Unit tests for core/parsers/ — file type detection, DataLoader registry,
and exception hierarchy.

Note: Full parser integration tests require VASP fixture files and
pymatgen. These tests focus on the framework-level behavior that can
be verified without external dependencies.
"""
import sys
import os
import tempfile
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.exceptions import (
    DbandError, AtomNotFoundError, OrbitalMissingError,
    MissingProjectedDOSError, FileTypeError, VASPKitAtomError,
)


# ── Exception hierarchy ─────────────────────────────────────────────

class TestExceptionHierarchy:
    """Verify all custom exceptions inherit from DbandError."""

    def test_atom_not_found_is_dband_error(self):
        err = AtomNotFoundError("Fe", ["Mo", "N", "P"])
        assert isinstance(err, DbandError)
        assert "Fe" in str(err)
        assert "Mo" in str(err)

    def test_orbital_missing_is_dband_error(self):
        err = OrbitalMissingError("/path/to/vasprun.xml", ["f-orbital"])
        assert isinstance(err, DbandError)
        assert "vasprun.xml" in str(err)
        assert "f-orbital" in str(err)

    def test_missing_pdos_is_dband_error(self):
        err = MissingProjectedDOSError("file1", "/path/to/file")
        assert isinstance(err, DbandError)
        assert "file1" in str(err)

    def test_file_type_error_is_dband_error(self):
        err = FileTypeError("/path/to/unknown.dat")
        assert isinstance(err, DbandError)
        assert "unknown.dat" in str(err)

    def test_vaspkit_atom_error(self):
        err = VASPKitAtomError("Fe", 5)
        assert isinstance(err, DbandError)
        assert "Fe" in str(err)
        assert "5" in str(err)

    def test_subclass_specificity(self):
        """Each subclass should have a distinct type name."""
        names = {
            type(AtomNotFoundError("x")).__name__,
            type(OrbitalMissingError("f", [])).__name__,
            type(MissingProjectedDOSError("x")).__name__,
            type(FileTypeError("x")).__name__,
            type(VASPKitAtomError("x", 1)).__name__,
        }
        assert len(names) == 5  # All unique


# ── DataLoader registry ─────────────────────────────────────────────

class TestDataLoaderRegistry:
    """Test the registry/strategy pattern without requiring pymatgen."""

    def test_register_custom_parser(self):
        """Verify that custom parsers can be registered."""
        from core.loader import DataLoader

        def fake_parser(filepath, atoms, spin, orbitals=None):
            import numpy as np
            e = np.array([0.0, 1.0])
            rho = {"dxy": np.array([1.0, 2.0])}
            return e, rho, 0.0

        DataLoader.register_parser("FAKE_FORMAT", fake_parser)
        assert "FAKE_FORMAT" in DataLoader._parsers

    def test_registry_contains_builtin_parsers(self):
        """Verify built-in parsers are registered."""
        from core.loader import DataLoader
        assert "vasprun.xml" in DataLoader._parsers
        assert "DOSCAR" in DataLoader._parsers
        assert "VASPKIT PDOS" in DataLoader._parsers


# ── File type detection (name-based, no pymatgen needed) ────────────

class TestFileDetection:
    """Test file type detection by filename (no I/O or pymatgen required)."""

    def test_detect_vasprun(self):
        from core.loader import DataLoader
        assert DataLoader.detect("/some/path/vasprun.xml") == "vasprun.xml"

    def test_detect_doscar(self):
        from core.loader import DataLoader
        assert DataLoader.detect("/some/path/DOSCAR") == "DOSCAR"

    def test_detect_vaspkit_pdos(self):
        from core.loader import DataLoader
        assert DataLoader.detect("/some/path/PDOS.dat") == "VASPKIT PDOS"

    def test_detect_unknown_raises(self):
        from core.loader import DataLoader
        with pytest.raises(FileTypeError):
            DataLoader.detect("/some/path/random.txt")


class TestParserInputValidation:
    """Regression tests for parser paths that can silently corrupt metrics."""

    def test_vaspkit_spin_partner_energy_axis_mismatch_raises(self):
        from core.parsers.vaspkit import parse_vaspkit_spin_all
        from core.parsers.constants import d_orb_names

        def write_pdos(path, energies):
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Energy dxy dyz dz2 dxz dx2-y2\n")
                for e in energies:
                    f.write(f"{e:.6f} 1.0 0.0 0.0 0.0 0.0\n")

        tmp_dir = tempfile.mkdtemp(prefix="dband_vaspkit_grid_")
        up = os.path.join(tmp_dir, "PDOS_A1_UP.dat")
        dw = os.path.join(tmp_dir, "PDOS_A1_DW.dat")
        write_pdos(up, [-1.0, 0.0, 1.0])
        write_pdos(dw, [-10.0, 0.0, 10.0])

        with pytest.raises(DbandError, match="energy axis"):
            parse_vaspkit_spin_all(up, "", orbitals=d_orb_names)

    def test_doscar_ragged_total_block_raises_instead_of_truncating(self):
        from core.parsers.doscar import _parse_float_block

        block = [
            "-1.0 1.0 0.0\n",
            "0.0 1.0\n",
            "1.0 1.0 2.0\n",
        ]

        with pytest.raises(DbandError, match="Ragged"):
            _parse_float_block(block, expected_rows=3, context="total DOS")

    def test_vasprun_structure_cache_key_changes_when_file_changes(self):
        from core.parsers.vasprun import _structure_cache_key

        tmp_dir = tempfile.mkdtemp(prefix="dband_vasprun_cache_")
        fp = os.path.join(tmp_dir, "vasprun.xml")
        with open(fp, "w", encoding="utf-8") as f:
            f.write("<modeling></modeling>")
        key1 = _structure_cache_key(fp)

        with open(fp, "w", encoding="utf-8") as f:
            f.write("<modeling><changed /></modeling>")
        key2 = _structure_cache_key(fp)

        assert key1 != key2


class TestDOSCARPhysicalLayout:
    """VASP projected-column layouts must be classified, never guessed."""

    def test_classifies_lm_nonspin_layout(self):
        from core.parsers.doscar import _classify_pdos_layout

        layout = _classify_pdos_layout(9, total_is_spin=False)
        assert layout.mode == "nonspin"
        assert layout.orbital_resolution == "lm"
        assert layout.components == ("total",)

    def test_classifies_lm_collinear_layout(self):
        from core.parsers.doscar import _classify_pdos_layout

        layout = _classify_pdos_layout(18, total_is_spin=True)
        assert layout.mode == "collinear"
        assert layout.orbital_resolution == "lm"
        assert layout.components == ("up", "down")

    def test_classifies_lm_noncollinear_layout(self):
        from core.parsers.doscar import _classify_pdos_layout

        layout = _classify_pdos_layout(36, total_is_spin=False)
        assert layout.mode == "noncollinear"
        assert layout.orbital_resolution == "lm"
        assert layout.components == ("total", "m1", "m2", "m3")

    def test_requires_mode_metadata_for_ambiguous_sixteen_column_layout(self):
        from core.parsers.doscar import _classify_pdos_layout

        with pytest.raises(DbandError, match="ambiguous"):
            _classify_pdos_layout(16, total_is_spin=False)

        nonspin = _classify_pdos_layout(
            16, total_is_spin=False, noncollinear_hint=False)
        assert (nonspin.mode, nonspin.orbital_resolution) == ("nonspin", "lm")

        noncollinear = _classify_pdos_layout(
            16, total_is_spin=False, noncollinear_hint=True)
        assert (noncollinear.mode, noncollinear.orbital_resolution) == ("noncollinear", "l")

    def test_rejects_unknown_projected_column_count(self):
        from core.parsers.doscar import _classify_pdos_layout

        with pytest.raises(DbandError, match="unsupported projected DOS layout"):
            _classify_pdos_layout(7, total_is_spin=False)


class TestNoncollinearProjection:
    def test_reconstructs_saxis_projected_spin_channels(self):
        from core.parsers.doscar import _project_noncollinear_spin

        total = np.array([4.0, 2.0])
        m3 = np.array([2.0, -1.0])
        up, down = _project_noncollinear_spin(total, m3)
        np.testing.assert_allclose(up, [3.0, 0.5])
        np.testing.assert_allclose(down, [1.0, 1.5])

    def test_rejects_unphysical_magnetization_density(self):
        from core.parsers.doscar import _project_noncollinear_spin

        with pytest.raises(DbandError, match="exceeds total DOS"):
            _project_noncollinear_spin(np.array([1.0]), np.array([1.1]))

    def test_accumulates_noncollinear_orbital_components(self):
        from core.parsers.doscar import _accumulate_noncollinear

        # lm layout: s, py, pz, px, dxy; each orbital has total,m1,m2,m3.
        first = np.zeros((2, 20))
        second = np.zeros((2, 20))
        first[:, 16:20] = [[4.0, 0.0, 0.0, 2.0], [2.0, 0.0, 0.0, -1.0]]
        second[:, 16:20] = [[2.0, 0.0, 0.0, 0.0], [4.0, 0.0, 0.0, 2.0]]
        components = _accumulate_noncollinear([first, second], [0, 1], ["dxy"])
        np.testing.assert_allclose(components["total"]["dxy"], [6.0, 6.0])
        np.testing.assert_allclose(components["m3"]["dxy"], [2.0, 1.0])

    def test_lorbit10_noncollinear_preserves_only_aggregate_d(self):
        from core.parsers.doscar import _accumulate_noncollinear

        # LORBIT=10 field order is s, p, d, f.  The d field is the third
        # four-component group; no m-resolved d orbital exists in this data.
        block = np.zeros((2, 16))
        block[:, 8:12] = [[4.0, 0.0, 0.0, 2.0], [2.0, 0.0, 0.0, -1.0]]
        components = _accumulate_noncollinear(
            [block], [0], ["d"], noncollinear_hint=True)

        np.testing.assert_allclose(components["total"]["d"], [4.0, 2.0])
        np.testing.assert_allclose(components["m3"]["d"], [2.0, -1.0])

    def test_doscar_lorbit10_noncollinear_uses_incar_metadata(self):
        from core.parsers.doscar import parse_doscar_spin_all

        tmp_dir = tempfile.mkdtemp(prefix="dband_ncl_lorbit10_")
        doscar = os.path.join(tmp_dir, "DOSCAR")
        incar = os.path.join(tmp_dir, "INCAR")
        with open(incar, "w", encoding="utf-8") as f:
            f.write("LNONCOLLINEAR = .TRUE.\nSAXIS = 0 0 1\n")
        rows = []
        for energy, total, m3 in [(-1.0, 4.0, 2.0), (1.0, 2.0, -1.0)]:
            values = [0.0] * 16
            values[8:12] = [total, 0.0, 0.0, m3]
            rows.append(f"{energy:.1f} " + " ".join(str(v) for v in values) + "\n")
        with open(doscar, "w", encoding="utf-8") as f:
            f.write("1 1 1 0\n0 0 0\n0\nCAR\nsynthetic\n")
            f.write("1 -1 2 0 1\n")
            f.write("-1.0 1.0 0.0\n1.0 1.0 1.0\n")
            f.write("1 -1 2 0 1\n")
            f.writelines(rows)

        energy, up, down, total, ef, metadata = parse_doscar_spin_all(
            doscar, "1", orbitals=["d"], return_metadata=True)
        np.testing.assert_allclose(energy, [-1.0, 1.0])
        np.testing.assert_allclose(total["d"], [4.0, 2.0])
        np.testing.assert_allclose(up["d"], [3.0, 0.5])
        np.testing.assert_allclose(down["d"], [1.0, 1.5])
        assert metadata.mode == "noncollinear"
        assert metadata.orbital_resolution == "l"
        assert metadata.spin_axis == (0.0, 0.0, 1.0)


class TestAggregateDResult:
    def test_result_marks_l_resolved_d_as_aggregate(self):
        from models.results import DbandResult

        result = DbandResult(
            label="LORBIT10", range_name="All", center=-1.0,
            width=1.0, filling=50.0, orb_weights={"d": 100.0},
            orb_centers={"d": -1.0}, orbital_resolution="l")

        assert result.is_aggregate_d is True

    def test_csv_leaves_unresolved_d_components_blank_for_lorbit10(self):
        from core.services.exporter import DataExporter
        from models.results import DbandResult

        tmp_dir = tempfile.mkdtemp(prefix="dband_export_lorbit10_")
        output = os.path.join(tmp_dir, "result.csv")
        DataExporter.export_results_csv([DbandResult(
            label="LORBIT10", range_name="All", center=-1.2, width=0.8,
            filling=50.0, orb_weights={"d": 100.0}, orb_centers={"d": -1.2},
            orbital_resolution="l")], output)

        with open(output, encoding="utf-8-sig", newline="") as f:
            rows = list(__import__("csv").reader(f))
        assert rows[1][5:10] == [""] * 5
        assert rows[1][10:15] == [""] * 5


class TestPDOSDisplaySelection:
    def test_l_resolved_data_display_only_aggregate_d(self):
        from ui.charts.pdos_chart import _display_d_orbitals

        assert _display_d_orbitals({"d": np.array([1.0, 2.0])}) == ["d"]
        assert _display_d_orbitals({"dxy": np.array([1.0, 2.0])}) == [
            "dxy", "dyz", "dz2", "dxz", "dx2-y2"]

    def test_multi_system_total_d_accepts_lorbit10_aggregate_channel(self):
        from ui.charts.multi_pdos_chart import MultiPDOSChartWidget

        result = MultiPDOSChartWidget._extract_dos(
            None, {"d": np.array([1.0, 2.0])}, "Total d-DOS", 2)
        np.testing.assert_allclose(result, [1.0, 2.0])


class TestLegacyPDOSStyleFingerprint:
    """New modes must not alter the existing PDOS visual contract."""

    def test_nonspin_default_artist_style_is_preserved(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ui.charts.pdos_chart import PDOSChartWidget
        from core.parsers.constants import d_orb_names

        app = QApplication.instance() or QApplication([])
        colors = {orb: f"#{i + 1:06d}" for i, orb in enumerate(d_orb_names)}
        chart = PDOSChartWidget(colors)
        energy = np.array([-1.0, 0.0, 1.0])
        up = {orb: np.full(3, index + 1.0) for index, orb in enumerate(d_orb_names)}
        chart.draw_pdos("legacy", {
            "energy": energy, "ef": 0.0, "up": up,
            "down": {orb: np.zeros(3) for orb in d_orb_names}, "has_spin": False,
        })

        ax = chart.fig.axes[0]
        pdos_lines = ax.lines[:5]
        assert [line.get_color() for line in pdos_lines] == [colors[orb] for orb in d_orb_names]
        assert [line.get_linewidth() for line in pdos_lines] == [1.0] * 5
        # Legacy non-spin cache still carries an all-zero down dictionary,
        # so the established renderer creates five mirrored zero fills too.
        assert len(ax.collections) == 10
        assert all(collection.get_alpha() == pytest.approx(0.5) for collection in ax.collections)
        assert ax.get_xlabel() == "E − E$_{f}$ (eV)"
        assert ax.get_ylabel() == "DOS"
        assert ax.lines[-2].get_linewidth() == pytest.approx(0.4)
        assert ax.lines[-1].get_linestyle() == "--"
        chart.deleteLater()


class TestVasprunNoncollinearLayout:
    """vasprun.xml PDOS rows must use their declared physical layout."""

    def test_classifies_scalar_and_noncollinear_partial_rows(self):
        from core.parsers.vasprun import _classify_vasprun_partial_layout

        assert _classify_vasprun_partial_layout(5, 5) == "scalar"
        assert _classify_vasprun_partial_layout(20, 5) == "noncollinear"

    def test_rejects_partial_row_with_unknown_width(self):
        from core.parsers.vasprun import _classify_vasprun_partial_layout

        with pytest.raises(DbandError, match="partial DOS row"):
            _classify_vasprun_partial_layout(7, 5)

    def test_accumulates_m3_before_reconstructing_saxis_channels(self):
        from core.parsers.vasprun import _accumulate_vasprun_noncollinear

        # Rows are total, m1, m2, m3 for each orbital.  The selected atoms
        # must be summed before rho_up/down are reconstructed.
        raw = {
            0: np.array([[4.0, 0.0, 0.0, 2.0], [2.0, 0.0, 0.0, -1.0]]),
            1: np.array([[2.0, 0.0, 0.0, 0.0], [4.0, 0.0, 0.0, 2.0]]),
        }
        up, down, total = _accumulate_vasprun_noncollinear(
            raw, [0, 1], ["dxy"], ["dxy"])

        np.testing.assert_allclose(total["dxy"], [6.0, 6.0])
        np.testing.assert_allclose(up["dxy"], [4.0, 3.5])
        np.testing.assert_allclose(down["dxy"], [2.0, 2.5])

    def test_l_decomposed_d_is_not_fabricated_as_five_d_orbitals(self):
        from core.parsers.vasprun import _field_targets

        assert _field_targets("d", ["d"]) == [("d", 1.0)]
        assert _field_targets("d", ["dxy", "dyz", "dz2", "dxz", "dx2-y2"]) == []


# ── Plugin system ───────────────────────────────────────────────────

class TestPluginSystem:
    """Test the plugin loader with a temporary plugin directory."""

    def _make_temp_dir(self):
        """Create a temporary directory (avoids pytest tmp_path permission issues)."""
        import tempfile
        d = tempfile.mkdtemp(prefix="dband_test_")
        return d

    def test_load_plugin_from_tempdir(self):
        """Create a temporary plugin file and verify it loads."""
        import os
        tmp_dir = self._make_temp_dir()
        plugin_code = '''
import numpy as np

def parse_test(filepath, atoms, spin, orbitals=None):
    e = np.array([0.0, 1.0])
    rho = {"dxy": np.array([1.0, 2.0])}
    return e, rho, 0.0

def register(loader):
    loader.register_parser("TEST_FORMAT", parse_test)
'''
        plugin_path = os.path.join(tmp_dir, "test_parser.py")
        with open(plugin_path, "w") as f:
            f.write(plugin_code)

        from core.plugins import PluginLoader
        PluginLoader.reset()

        loaded = PluginLoader.load_all(tmp_dir)
        assert "test_parser" in loaded
        assert PluginLoader.LOADED is True

    def test_skip_files_without_register(self):
        """Files without register() should be skipped gracefully."""
        import os
        tmp_dir = self._make_temp_dir()
        plugin_path = os.path.join(tmp_dir, "bad_plugin.py")
        with open(plugin_path, "w") as f:
            f.write("# No register function here\nx = 42\n")

        from core.plugins import PluginLoader
        PluginLoader.reset()

        loaded = PluginLoader.load_all(tmp_dir)
        assert "bad_plugin" not in loaded

    def test_nonexistent_directory(self):
        """Loading from a nonexistent directory should return empty list."""
        from core.plugins import PluginLoader
        PluginLoader.reset()

        loaded = PluginLoader.load_all("/nonexistent/path/12345")
        assert loaded == []


# ── Workspace serialization ─────────────────────────────────────────

class TestWorkspaceSerialization:
    """Test AppState save/load round-trip."""

    def _make_temp_dir(self):
        import tempfile
        return tempfile.mkdtemp(prefix="dband_ws_test_")

    def test_save_load_roundtrip(self):
        from models.app_state import AppState
        from models.results import DbandResult
        import os

        state = AppState()
        state.file_entries = [
            {"path": "/path/to/vasprun.xml", "label": "Mo-N2P2"},
            {"path": "/path/to/DOSCAR", "label": "Mo-N3P"},
        ]
        state.results_data = [
            DbandResult(label="Mo-N2P2", range_name="All", center=-2.5,
                        width=1.8, filling=75.0,
                        orb_weights={"dxy": 0.2}, orb_centers={"dxy": -2.3}),
        ]
        state.active_theme = "Custom Theme"
        state.params = {"atoms": "1,2,3", "spin": "total"}

        tmp_dir = self._make_temp_dir()
        ws_path = os.path.join(tmp_dir, "workspace.json")
        state.save_workspace(ws_path)

        # Load into a new state
        state2 = AppState()
        state2.load_workspace(ws_path)

        assert state2.file_entries == state.file_entries
        assert len(state2.results_data) == 1
        assert state2.results_data[0].label == "Mo-N2P2"
        assert state2.results_data[0].center == -2.5
        assert state2.active_theme == "Custom Theme"
        assert state2.params == state.params

    def test_load_nonexistent_raises(self):
        from models.app_state import AppState
        state = AppState()
        with pytest.raises(FileNotFoundError):
            state.load_workspace("/nonexistent/workspace.json")


# ── Memory-aware LRU cache ──────────────────────────────────────────

class TestMemoryAwareLRU:
    """Test the memory-aware LRU cache eviction logic."""

    def test_eviction_by_memory(self):
        from models.app_state import MemoryAwareLRUCache
        import numpy as np

        # 1 MB limit
        cache = MemoryAwareLRUCache(max_memory_mb=1)
        # Each entry: 100k float64 = 800 KB
        big_arr = np.zeros(100_000, dtype=np.float64)
        cache["a"] = {"energy": big_arr.copy()}
        cache["b"] = {"energy": big_arr.copy()}  # Should evict "a"
        assert "a" not in cache
        assert "b" in cache

    def test_lru_order(self):
        """Accessing an item should move it to the end (keep it)."""
        from models.app_state import MemoryAwareLRUCache
        import numpy as np

        cache = MemoryAwareLRUCache(max_memory_mb=1)
        arr = np.zeros(50_000, dtype=np.float64)  # ~400 KB
        cache["a"] = {"energy": arr.copy()}
        cache["b"] = {"energy": arr.copy()}  # ~800 KB total, fits

        # Access "a" to make it recently used
        _ = cache["a"]

        # Adding "c" should evict "b" (least recently used), not "a"
        cache["c"] = {"energy": arr.copy()}
        assert "a" in cache
        assert "b" not in cache

    def test_estimate_size(self):
        from models.app_state import MemoryAwareLRUCache
        import numpy as np

        arr = np.zeros(1000, dtype=np.float64)
        size = MemoryAwareLRUCache._estimate_size({"energy": arr})
        assert size == 8000  # 1000 * 8 bytes


# ── HybridizationWorker cache-key isolation ─────────────────────────

class TestHybridizationCacheIsolation:
    """C5 regression: shared_cache is keyed by user-editable *label*.

    Two files that happen to share a label (e.g. the user names both
    "Pt(111)") must NOT cross-contaminate.  The fix requires the cached
    entry's stored ``filepath`` to equal the current file's path; a label
    collision with a different path falls through to a correct full re-parse.

    We mock DataLoader.load_spin_all to observe whether the worker hits the
    cache (no call) or re-parses (one call), without needing real VASP files.
    """

    def _make_worker(self):
        from core.services.hybridization_worker import HybridizationWorker
        # params: (label, fp, atoms, orbitals, spin, alias)
        return HybridizationWorker.__new__(HybridizationWorker)

    def test_shared_cache_rejects_label_collision_with_different_filepath(self):
        import numpy as np
        from unittest import mock

        worker = self._make_worker()
        worker._local_cache = {}

        energy = np.linspace(-5, 5, 50)
        ef = 0.0
        # Stale shared-cache entry written under label="X" but for /OLD.xml.
        worker._shared_cache = {
            "X": {
                "atoms": "1",
                "filepath": "/OLD.xml",   # different from the request below
                "energy": energy, "ef": ef,
                "up": {"dxy": np.ones(50)},
                "down": {"dxy": np.zeros(50)},
                "has_spin": False,
            }
        }

        # Request the SAME label "X" but a DIFFERENT filepath → must NOT hit.
        params = ("X", "/NEW.xml", "1", ["dxy"], "up", "X-alias")

        reparse_calls = []
        def fake_load(fp, atoms, orbitals=None):
            reparse_calls.append((fp, atoms))
            return energy, {"dxy": np.full(50, 9.0)}, {"dxy": np.zeros(50)}, {}, ef

        with mock.patch(
            "core.services.hybridization_worker.DataLoader"
        ) as MockLoader:
            MockLoader.load_spin_all = fake_load
            e, r_up, r_dn, orbs, alias = worker._parse_with_cache(params)

        # Must have triggered a full re-parse (cache miss), and the result
        # must reflect the NEW file's data (9.0), not the stale 1.0.
        assert len(reparse_calls) == 1
        assert reparse_calls[0][0] == "/NEW.xml"
        assert np.allclose(r_up["dxy"], 9.0)

    def test_shared_cache_hit_when_filepath_matches(self):
        import numpy as np
        from unittest import mock

        worker = self._make_worker()
        worker._local_cache = {}
        energy = np.linspace(-5, 5, 50)
        worker._shared_cache = {
            "X": {
                "atoms": "1",
                "filepath": "/SAME.xml",   # matches the request
                "energy": energy, "ef": 0.0,
                "up": {"dxy": np.full(50, 7.0)},
                "down": {"dxy": np.zeros(50)},
                "has_spin": False,
            }
        }
        params = ("X", "/SAME.xml", "1", ["dxy"], "up", "X-alias")

        with mock.patch(
            "core.services.hybridization_worker.DataLoader"
        ) as MockLoader:
            # If the cache is hit, load_spin_all must never be called.
            MockLoader.load_spin_all = mock.Mock(
                side_effect=AssertionError("cache miss should not re-parse"))
            e, r_up, r_dn, orbs, alias = worker._parse_with_cache(params)

        # Hit returns the cached value (7.0).
        assert np.allclose(r_up["dxy"], 7.0)
