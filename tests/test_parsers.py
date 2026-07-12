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


def test_pdos_capabilities_exposes_honest_projection_contract():
    from core.pdos_metadata import PDOSCapabilities

    caps = PDOSCapabilities(
        source_format="DOSCAR",
        vasp_version="6.4.3",
        spin_mode="nonspin",
        orbital_resolution="l",
        available_orbitals=("s", "p", "d", "f"),
        structure_available=False,
        atom_selection_modes=("index",),
        field_source="doscar_layout",
        warnings=("No matching structure file; use numeric atom indices.",),
    )

    assert caps.supports_orbital("d")
    assert not caps.supports_orbital("dxy")
    assert caps.can_select_elements is False


def test_pdos_metadata_keeps_old_constructor_and_accepts_capabilities():
    from core.pdos_metadata import PDOSCapabilities, PDOSMetadata

    legacy = PDOSMetadata(
        mode="nonspin", orbital_resolution="lm", spin_axis=None,
        source_format="vasprun.xml")
    assert legacy.capabilities is None

    caps = PDOSCapabilities(
        source_format="vasprun.xml", vasp_version=None, spin_mode="nonspin",
        orbital_resolution="lm", available_orbitals=("s", "py"),
        structure_available=True, atom_selection_modes=("index", "element"),
        field_source="declared", warnings=())
    assert PDOSMetadata(
        mode="nonspin", orbital_resolution="lm", spin_axis=None,
        source_format="vasprun.xml", capabilities=caps).capabilities == caps


def test_structured_parser_errors_include_actionable_context():
    from core.exceptions import AmbiguousLayoutError, OrbitalUnavailableError

    ambiguous = AmbiguousLayoutError(
        "DOSCAR", 16,
        "Provide matching INCAR or vasprun.xml with LSORBIT/LNONCOLLINEAR.")
    assert "16" in str(ambiguous)
    assert "INCAR" in str(ambiguous)

    missing = OrbitalUnavailableError("dxy", ("s", "p", "d"))
    assert "dxy" in str(missing)
    assert "d" in str(missing)


def test_data_loader_inspects_doscar_before_calculation():
    from core.loader import DataLoader

    tmp_dir = tempfile.mkdtemp(prefix="dband_inspect_doscar_")
    path = os.path.join(tmp_dir, "DOSCAR")
    orbitals = " ".join("0.0" for _ in range(9))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("1 1 1 0\n0 0 0\n0\nCAR\nsynthetic\n")
        handle.write("1 -1 2 0 1\n")
        handle.write("-1.0 1.0 0.0\n1.0 1.0 1.0\n")
        handle.write("1 -1 2 0 1\n")
        handle.write(f"-1.0 {orbitals}\n1.0 {orbitals}\n")

    caps = DataLoader.inspect(path)

    assert caps.source_format == "DOSCAR"
    assert caps.spin_mode == "nonspin"
    assert caps.orbital_resolution == "lm"
    assert caps.available_orbitals == (
        "s", "py", "pz", "px", "dxy", "dyz", "dz2", "dxz", "dx2-y2")
    assert caps.atom_selection_modes == ("index",)
    assert caps.warnings


def test_data_loader_inspect_respects_declared_type():
    from core.loader import DataLoader

    tmp_dir = tempfile.mkdtemp(prefix="dband_inspect_declared_")
    path = os.path.join(tmp_dir, "unusual-name")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Energy dxy dyz dz2 dxz dx2-y2\n0 1 1 1 1 1\n")

    caps = DataLoader.inspect(path, declared_type="VASPKIT PDOS")
    assert caps.source_format == "VASPKIT PDOS"
    assert set(caps.available_orbitals) == {"dxy", "dyz", "dz2", "dxz", "dx2-y2"}


def test_file_manager_runs_preflight_and_stores_serializable_capabilities():
    from PySide6.QtWidgets import QApplication
    from models.app_state import AppState
    from ui.panels.file_manager import FileManagerPanel

    app = QApplication.instance() or QApplication([])

    tmp_dir = tempfile.mkdtemp(prefix="dband_file_panel_preflight_")
    path = os.path.join(tmp_dir, "PDOS_test.dat")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Energy dxy dyz dz2 dxz dx2-y2\n0 1 1 1 1 1\n")

    state = AppState()
    panel = FileManagerPanel(state)
    panel.import_paths([path])

    entry = state.file_entries[0]
    assert entry["inspection_error"] == ""
    assert entry["capabilities"]["source_format"] == "VASPKIT PDOS"
    assert entry["capabilities"]["available_orbitals"] == (
        "dxy", "dyz", "dz2", "dxz", "dx2-y2")
    assert panel.list_files.item(0, 2).text() == "Ready · lm"


def test_file_manager_keeps_blocked_file_with_actionable_diagnostic():
    from PySide6.QtWidgets import QApplication
    from models.app_state import AppState
    from ui.panels.file_manager import FileManagerPanel

    app = QApplication.instance() or QApplication([])

    tmp_dir = tempfile.mkdtemp(prefix="dband_file_panel_blocked_")
    path = os.path.join(tmp_dir, "DOSCAR")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("broken\n")

    state = AppState()
    panel = FileManagerPanel(state)
    panel.import_paths([path])

    assert state.file_entries[0]["inspection_error"]
    assert panel.list_files.item(0, 2).text() == "Blocked"


def _write_minimal_doscar(path, *, ions=1, projected_columns=9, spin=False):
    total_rows = (
        ["-1.0 1.0 1.0 0.0 0.0\n", "1.0 1.0 1.0 1.0 1.0\n"]
        if spin else ["-1.0 1.0 0.0\n", "1.0 1.0 1.0\n"])
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"{ions} {ions} 1 0\n0 0 0\n0\nCAR\nprivacy-test\n")
        handle.write("1 -1 2 0 1\n")
        handle.writelines(total_rows)
        values = " ".join("0.1" for _ in range(projected_columns))
        for _ in range(ions):
            handle.write("1 -1 2 0 1\n")
            handle.write(f"-1.0 {values}\n1.0 {values}\n")


def test_pdos_input_context_records_only_explicitly_authorized_files():
    from core.pdos_metadata import PDOSInputContext

    context = PDOSInputContext(
        primary_path="D:/calc/DOSCAR", source_format="DOSCAR",
        structure_path="D:/chosen/POSCAR", metadata_path=None)
    assert context.authorized_paths == (
        "D:/calc/DOSCAR", "D:/chosen/POSCAR")


def test_doscar_numeric_inspection_ignores_unrelated_neighbor_structure():
    from core.loader import DataLoader

    tmp_dir = tempfile.mkdtemp(prefix="dband_privacy_numeric_")
    doscar = os.path.join(tmp_dir, "DOSCAR")
    _write_minimal_doscar(doscar, ions=2)
    with open(os.path.join(tmp_dir, "CONTCAR"), "w", encoding="utf-8") as handle:
        handle.write("not authorized and not a valid structure\n")

    caps = DataLoader.inspect(doscar)

    assert caps.structure_available is False
    assert caps.atom_selection_modes == ("index",)


def test_doscar_reads_and_validates_only_explicit_structure():
    from core.loader import DataLoader
    from core.pdos_metadata import PDOSInputContext

    tmp_dir = tempfile.mkdtemp(prefix="dband_privacy_explicit_structure_")
    doscar = os.path.join(tmp_dir, "DOSCAR")
    structure = os.path.join(tmp_dir, "chosen.vasp")
    _write_minimal_doscar(doscar, ions=2)
    with open(structure, "w", encoding="utf-8") as handle:
        handle.write("invalid explicit structure\n")
    context = PDOSInputContext(
        primary_path=doscar, source_format="DOSCAR", structure_path=structure)

    with pytest.raises(DbandError, match="chosen.vasp"):
        DataLoader.inspect(context)


def test_doscar_inspection_names_explicit_mismatched_structure():
    from core.loader import DataLoader
    from core.pdos_metadata import PDOSInputContext

    tmp_dir = tempfile.mkdtemp(prefix="dband_named_mismatch_")
    doscar = os.path.join(tmp_dir, "DOSCAR")
    structure = os.path.join(tmp_dir, "selected-CONTCAR")
    _write_minimal_doscar(doscar, ions=2)
    with open(structure, "w", encoding="utf-8") as handle:
        handle.write("one atom\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n")

    with pytest.raises(DbandError, match="selected-CONTCAR"):
        DataLoader.inspect(PDOSInputContext(
            doscar, "DOSCAR", structure_path=structure))


def test_doscar_does_not_read_neighbor_incar_without_authorization():
    from core.exceptions import AmbiguousLayoutError
    from core.loader import DataLoader
    from core.pdos_metadata import PDOSInputContext

    tmp_dir = tempfile.mkdtemp(prefix="dband_privacy_metadata_")
    doscar = os.path.join(tmp_dir, "DOSCAR")
    incar = os.path.join(tmp_dir, "INCAR")
    _write_minimal_doscar(doscar, projected_columns=16, spin=False)
    with open(incar, "w", encoding="utf-8") as handle:
        handle.write("LNONCOLLINEAR = .TRUE.\nLSORBIT = .TRUE.\n")

    with pytest.raises(AmbiguousLayoutError):
        DataLoader.inspect(doscar)

    caps = DataLoader.inspect(PDOSInputContext(
        primary_path=doscar, source_format="DOSCAR", metadata_path=incar))
    assert caps.spin_mode == "noncollinear"


def test_data_loader_parses_numeric_doscar_context_without_neighbor_structure():
    from core.loader import DataLoader
    from core.pdos_metadata import PDOSInputContext

    tmp_dir = tempfile.mkdtemp(prefix="dband_context_load_")
    doscar = os.path.join(tmp_dir, "DOSCAR")
    _write_minimal_doscar(doscar, ions=2)
    with open(os.path.join(tmp_dir, "CONTCAR"), "w", encoding="utf-8") as handle:
        handle.write("wrong\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n")

    context = PDOSInputContext(primary_path=doscar, source_format="DOSCAR")
    energy, up, down, total, ef = DataLoader.load_spin_all(
        context, "1", orbitals=["dxy"])

    assert len(energy) == 2
    assert np.all(total["dxy"] > 0)


def test_data_loader_rejects_explicit_mismatched_structure_for_doscar():
    from core.loader import DataLoader
    from core.pdos_metadata import PDOSInputContext

    tmp_dir = tempfile.mkdtemp(prefix="dband_context_mismatch_")
    doscar = os.path.join(tmp_dir, "DOSCAR")
    structure = os.path.join(tmp_dir, "selected-CONTCAR")
    _write_minimal_doscar(doscar, ions=2)
    with open(structure, "w", encoding="utf-8") as handle:
        handle.write("one atom\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n")

    context = PDOSInputContext(
        primary_path=doscar, source_format="DOSCAR", structure_path=structure)
    with pytest.raises(DbandError, match="selected-CONTCAR"):
        DataLoader.load_spin_all(context, "1", orbitals=["dxy"])


def test_vasprun_inspection_does_not_probe_neighbor_structure():
    from core.loader import DataLoader

    tmp_dir = tempfile.mkdtemp(prefix="dband_vasprun_privacy_")
    path = os.path.join(tmp_dir, "vasprun.xml")
    with open(os.path.join(tmp_dir, "POSCAR"), "w", encoding="utf-8") as handle:
        handle.write("unauthorized neighbor\n")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("""<modeling><generator><i name='version'>6.4</i></generator>
<parameters><i name='ISPIN'>1</i></parameters><calculation><dos><partial><array>
<field>energy</field><field>s</field><field>py</field><field>pz</field><field>px</field>
<field>dxy</field><field>dyz</field><field>dz2</field><field>dxz</field><field>x2-y2</field>
<set><set comment='ion 1'><set comment='spin 1'><r>0 1 1 1 1 1 1 1 1 1</r>
</set></set></set></array></partial></dos></calculation></modeling>""")

    caps = DataLoader.inspect(path)
    assert caps.structure_available is False
    assert caps.atom_selection_modes == ("index",)


def test_vaspkit_inspection_does_not_probe_neighbor_structure():
    from core.loader import DataLoader

    tmp_dir = tempfile.mkdtemp(prefix="dband_vaspkit_privacy_")
    path = os.path.join(tmp_dir, "PDOS_test.dat")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Energy dxy dyz dz2 dxz dx2-y2\n0 1 1 1 1 1\n")
    with open(os.path.join(tmp_dir, "CONTCAR"), "w", encoding="utf-8") as handle:
        handle.write("unauthorized neighbor\n")

    caps = DataLoader.inspect(path)
    assert caps.structure_available is False


def test_vaspkit_does_not_open_implicit_spin_partner():
    from core.loader import DataLoader
    from core.pdos_metadata import PDOSInputContext

    tmp_dir = tempfile.mkdtemp(prefix="dband_vaspkit_partner_privacy_")
    up = os.path.join(tmp_dir, "PDOS_A1_UP.dat")
    down = os.path.join(tmp_dir, "PDOS_A1_DW.dat")
    with open(up, "w", encoding="utf-8") as handle:
        handle.write("# Energy dxy dyz dz2 dxz dx2-y2\n-1 1 1 1 1 1\n0 1 1 1 1 1\n")
    with open(down, "w", encoding="utf-8") as handle:
        handle.write("# Energy dxy dyz dz2 dxz dx2-y2\n-9 2 2 2 2 2\n9 2 2 2 2 2\n")

    result = DataLoader.load_spin_all(
        PDOSInputContext(up, "VASPKIT PDOS"), "1", orbitals=["dxy"])
    assert np.all(result[2]["dxy"] == 0)

    with pytest.raises(DbandError, match="energy axis"):
        DataLoader.load_spin_all(
            PDOSInputContext(
                up, "VASPKIT PDOS", spin_partner_path=down),
            "1", orbitals=["dxy"])


def test_file_entry_builds_explicit_context_without_directory_discovery():
    from core.pdos_metadata import input_context_from_entry

    entry = {
        "path": "D:/calc/DOSCAR", "label": "sample",
        "auxiliary_files": {
            "structure": "D:/authorized/POSCAR",
            "metadata": None,
            "spin_partner": None,
        },
    }
    context = input_context_from_entry(entry, "DOSCAR")
    assert context.primary_path == "D:/calc/DOSCAR"
    assert context.structure_path == "D:/authorized/POSCAR"
    assert context.metadata_path is None


def test_file_manager_marks_ambiguous_doscar_as_needs_input():
    from PySide6.QtWidgets import QApplication
    from models.app_state import AppState
    from ui.panels.file_manager import FileManagerPanel

    app = QApplication.instance() or QApplication([])
    tmp_dir = tempfile.mkdtemp(prefix="dband_needs_input_")
    path = os.path.join(tmp_dir, "DOSCAR")
    _write_minimal_doscar(path, projected_columns=16, spin=False)

    state = AppState()
    panel = FileManagerPanel(state)
    panel.import_paths([path])

    assert state.file_entries[0]["inspection_status"] == "needs_input"
    assert panel.list_files.item(0, 2).text() == "Needs input"


def test_workspace_migrates_old_entries_without_auxiliary_authorization():
    from models.app_state import AppState

    tmp_dir = tempfile.mkdtemp(prefix="dband_workspace_privacy_")
    path = os.path.join(tmp_dir, "old.json")
    with open(path, "w", encoding="utf-8") as handle:
        __import__("json").dump({
            "version": "1.0",
            "file_entries": [{"path": "D:/calc/DOSCAR", "label": "old"}],
        }, handle)

    state = AppState()
    with pytest.warns(UserWarning):
        state.load_workspace(path)

    assert state._WORKSPACE_VERSION == "1.1"
    assert state.file_entries[0]["auxiliary_files"] == {
        "structure": None, "metadata": None, "spin_partner": None}


def test_context_fingerprint_changes_with_explicit_auxiliary_file():
    from core.pdos_metadata import PDOSInputContext
    from core.services.file_identity import context_fingerprint

    tmp_dir = tempfile.mkdtemp(prefix="dband_context_fingerprint_")
    primary = os.path.join(tmp_dir, "DOSCAR")
    metadata = os.path.join(tmp_dir, "INCAR")
    with open(primary, "w", encoding="utf-8") as handle:
        handle.write("primary")
    with open(metadata, "w", encoding="utf-8") as handle:
        handle.write("LSORBIT = F")
    context = PDOSInputContext(
        primary, "DOSCAR", metadata_path=metadata)
    before = context_fingerprint(context)
    with open(metadata, "a", encoding="utf-8") as handle:
        handle.write("\nchanged")
    after = context_fingerprint(context)
    assert before != after


def test_doscar_inspection_opens_only_authorized_primary_file(monkeypatch):
    import builtins
    from core.loader import DataLoader
    from core.pdos_metadata import PDOSInputContext

    tmp_dir = tempfile.mkdtemp(prefix="dband_access_audit_")
    doscar = os.path.join(tmp_dir, "DOSCAR")
    neighbor = os.path.join(tmp_dir, "CONTCAR")
    _write_minimal_doscar(doscar, ions=1)
    with open(neighbor, "w", encoding="utf-8") as handle:
        handle.write("private neighbor")
    real_open = builtins.open
    opened = []

    def audited_open(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)):
            opened.append(os.path.abspath(os.fspath(path)))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", audited_open)
    DataLoader.inspect(PDOSInputContext(doscar, "DOSCAR"))

    assert os.path.abspath(neighbor) not in opened
    assert os.path.abspath(doscar) in opened

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

    def test_detects_renamed_doscar_by_content(self):
        from core.loader import DataLoader

        tmp_dir = tempfile.mkdtemp(prefix="dband_renamed_doscar_")
        path = os.path.join(tmp_dir, "DOSCAR(3)")
        _write_minimal_doscar(path, ions=1)
        assert DataLoader.detect(path) == "DOSCAR"


def test_file_manager_explicit_metadata_resolves_needs_input():
    from PySide6.QtWidgets import QApplication
    from models.app_state import AppState
    from ui.panels.file_manager import FileManagerPanel

    app = QApplication.instance() or QApplication([])
    tmp_dir = tempfile.mkdtemp(prefix="dband_explicit_metadata_ui_")
    path = os.path.join(tmp_dir, "DOSCAR")
    metadata = os.path.join(tmp_dir, "chosen-INCAR")
    _write_minimal_doscar(path, projected_columns=16, spin=False)
    with open(metadata, "w", encoding="utf-8") as handle:
        handle.write("LNONCOLLINEAR = .TRUE.\nLSORBIT = .TRUE.\n")

    state = AppState()
    panel = FileManagerPanel(state)
    panel.import_paths([path])
    panel.set_auxiliary_file(0, "metadata", metadata)

    assert state.file_entries[0]["inspection_status"] == "ready"
    assert state.file_entries[0]["auxiliary_files"]["metadata"] == metadata
    assert panel.list_files.item(0, 2).text().startswith("Ready")


def test_file_manager_displays_needs_input_reason_without_hovering():
    from PySide6.QtWidgets import QApplication
    from models.app_state import AppState
    from ui.panels.file_manager import FileManagerPanel

    app = QApplication.instance() or QApplication([])
    tmp_dir = tempfile.mkdtemp(prefix="dband_visible_diagnostic_")
    path = os.path.join(tmp_dir, "DOSCAR")
    _write_minimal_doscar(path, projected_columns=16, spin=False)
    panel = FileManagerPanel(AppState())
    panel.import_paths([path])

    assert "metadata" in panel.lbl_diagnostic.text().lower()
    assert panel.lbl_diagnostic.isVisibleTo(panel)


def test_copy_details_shows_visible_confirmation():
    from PySide6.QtWidgets import QApplication
    from models.app_state import AppState
    from ui.panels.file_manager import FileManagerPanel

    app = QApplication.instance() or QApplication([])
    state = AppState()
    state.file_entries = [{
        "path": "D:/calc/DOSCAR", "label": "sample",
        "inspection_status": "ready", "inspection_error": "",
        "capabilities": {
            "source_format": "DOSCAR", "spin_mode": "nonspin",
            "orbital_resolution": "lm", "available_orbitals": ("dxy",),
            "warnings": (),
        },
        "auxiliary_files": {
            "structure": None, "metadata": None, "spin_partner": None},
    }]
    panel = FileManagerPanel(state)
    panel._refresh_file_list()
    panel.list_files.selectRow(0)

    panel.copy_selected_details()

    assert panel.btn_copy.text() == "Copied"
    assert "copied" in panel.lbl_diagnostic.text().lower()
    assert "D:/calc/DOSCAR" in QApplication.clipboard().text()


class TestParserInputValidation:
    """Regression tests for parser paths that can silently corrupt metrics."""

    def test_vaspkit_spin_partner_energy_axis_mismatch_raises(self):
        from core.parsers.vaspkit import parse_vaspkit_spin_all
        from core.parsers.constants import d_orb_names
        from core.pdos_metadata import PDOSInputContext

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
            parse_vaspkit_spin_all(
                up, "", orbitals=d_orb_names,
                input_context=PDOSInputContext(
                    up, "VASPKIT PDOS", spin_partner_path=dw))

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


class TestVasprunFieldRecovery:
    def test_infers_unique_lorbit11_spd_layout_without_fields(self):
        from core.parsers.vasprun import _infer_vasprun_fields

        fields, source = _infer_vasprun_fields(9, noncollinear_hint=None)
        assert fields == [
            "s", "py", "pz", "px", "dxy", "dyz", "dz2", "dxz", "dx2-y2"]
        assert source == "known_layout"

    def test_rejects_ambiguous_sixteen_column_layout_without_metadata(self):
        from core.exceptions import AmbiguousLayoutError
        from core.parsers.vasprun import _infer_vasprun_fields

        with pytest.raises(AmbiguousLayoutError, match="INCAR"):
            _infer_vasprun_fields(16, noncollinear_hint=None)

    def test_resolves_sixteen_columns_with_noncollinear_metadata(self):
        from core.parsers.vasprun import _infer_vasprun_fields

        scalar, _ = _infer_vasprun_fields(16, noncollinear_hint=False)
        noncollinear, _ = _infer_vasprun_fields(16, noncollinear_hint=True)
        assert len(scalar) == 16
        assert noncollinear == ["s", "p", "d", "f"]

    def test_inspects_vasprun_fields_independent_of_node_order(self):
        from core.loader import DataLoader

        tmp_dir = tempfile.mkdtemp(prefix="dband_inspect_vasprun_")
        path = os.path.join(tmp_dir, "vasprun.xml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("""<?xml version='1.0'?>
<modeling>
  <generator><i name='version'>6.4.3</i></generator>
  <parameters><i name='LNONCOLLINEAR'>F</i><i name='LSORBIT'>F</i></parameters>
  <calculation><dos><partial><array>
    <set><set comment='ion 1'><set comment='spin 1'>
      <r>-1 1 2 3 4 5 6 7 8 9</r>
    </set></set></set>
    <field>energy</field><field>s</field><field>py</field><field>pz</field>
    <field>px</field><field>dxy</field><field>dyz</field><field>dz2</field>
    <field>dxz</field><field>x2-y2</field>
  </array></partial></dos></calculation>
</modeling>""")

        caps = DataLoader.inspect(path)
        assert caps.vasp_version == "6.4.3"
        assert caps.field_source == "declared"
        assert caps.spin_mode == "nonspin"
        assert caps.available_orbitals[-1] == "dx2-y2"


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
        from core.pdos_metadata import PDOSInputContext

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
            doscar, "1", orbitals=["d"], return_metadata=True,
            input_context=PDOSInputContext(
                doscar, "DOSCAR", metadata_path=incar))
        np.testing.assert_allclose(energy, [-1.0, 1.0])
        np.testing.assert_allclose(total["d"], [4.0, 2.0])
        np.testing.assert_allclose(up["d"], [3.0, 0.5])
        np.testing.assert_allclose(down["d"], [1.0, 1.5])
        assert metadata.mode == "noncollinear"
        assert metadata.orbital_resolution == "l"
        assert metadata.spin_axis == (0.0, 0.0, 1.0)
        assert metadata.capabilities.available_orbitals == ("s", "p", "d", "f")
        assert metadata.capabilities.field_source == "doscar_layout"


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

    def test_csv_exports_calculation_provenance(self):
        from core.services.exporter import DataExporter
        from models.results import DbandResult

        tmp_dir = tempfile.mkdtemp(prefix="dband_export_provenance_")
        output = os.path.join(tmp_dir, "result.csv")
        DataExporter.export_results_csv([DbandResult(
            label="SOC", range_name="[-5,2]", center=-1.2, width=0.8,
            filling=50.0, source_format="DOSCAR", spin_mode="noncollinear",
            orbital_resolution="lm", integration_method="simpson",
            vasp_version="6.4.3", field_source="doscar_layout")], output)

        with open(output, encoding="utf-8-sig", newline="") as handle:
            rows = list(__import__("csv").reader(handle))
        assert rows[0][-6:] == [
            "Source Format", "VASP Version", "Spin Mode",
            "Orbital Resolution", "Field Source", "Integration Method"]
        assert rows[1][-6:] == [
            "DOSCAR", "6.4.3", "noncollinear", "lm",
            "doscar_layout", "simpson"]

    def test_csv_exports_explicit_auxiliary_provenance_without_hidden_files(self):
        from core.services.exporter import DataExporter
        from models.results import DbandResult

        tmp_dir = tempfile.mkdtemp(prefix="dband_export_aux_provenance_")
        output = os.path.join(tmp_dir, "result.csv")
        DataExporter.export_results_csv([DbandResult(
            label="explicit", range_name="All", center=-1.0, width=1.0,
            filling=50.0, structure_source="selected-POSCAR",
            metadata_source="selected-INCAR", saxis_source="selected-INCAR")], output)
        with open(output, encoding="utf-8-sig", newline="") as handle:
            rows = list(__import__("csv").reader(handle))
        assert rows[0][15:18] == [
            "Structure Source", "Metadata Source", "SAXIS Source"]
        assert rows[1][15:18] == [
            "selected-POSCAR", "selected-INCAR", "selected-INCAR"]


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

        assert [entry["path"] for entry in state2.file_entries] == [
            entry["path"] for entry in state.file_entries]
        assert all(entry["auxiliary_files"] == {
            "structure": None, "metadata": None, "spin_partner": None}
            for entry in state2.file_entries)
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

    def test_shared_cache_rejects_missing_file_fingerprint(self):
        """Legacy cache entries cannot prove that an overwritten file is unchanged."""
        import numpy as np
        from unittest import mock

        worker = self._make_worker()
        worker._local_cache = {}
        energy = np.linspace(-5, 5, 50)
        worker._shared_cache = {
            "X": {
                "atoms": "1",
                "filepath": "/SAME.xml",
                "energy": energy, "ef": 0.0,
                "up": {"dxy": np.full(50, 7.0)},
                "down": {"dxy": np.zeros(50)},
                "has_spin": False,
            }
        }
        params = ("X", "/SAME.xml", "1", ["dxy"], "up", "X-alias")

        with mock.patch("core.services.hybridization_worker.DataLoader") as MockLoader:
            MockLoader.load_spin_all.return_value = (
                energy, {"dxy": np.full(50, 9.0)}, {"dxy": np.zeros(50)}, {}, 0.0)
            _, r_up, _, _, _ = worker._parse_with_cache(params)

        assert MockLoader.load_spin_all.call_count == 1
        assert np.allclose(r_up["dxy"], 9.0)

    def test_shared_cache_hit_when_filepath_and_fingerprint_match(self):
        import numpy as np
        from unittest import mock

        worker = self._make_worker()
        worker._local_cache = {}
        energy = np.linspace(-5, 5, 50)
        worker._shared_cache = {
            "X": {
                "atoms": "1",
                "filepath": "/SAME.xml",   # matches the request
                "file_fingerprint": (0, 0),  # nonexistent test path
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
