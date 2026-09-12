"""Regression tests for hybridization task state and geometry diagnostics."""

import os
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_geometry_rejection_reports_the_selected_non_xml_source():
    """A DOSCAR selection must not be misreported as an absent vasprun.xml."""
    from core.services.hybridization_worker import geometry_input_diagnostic

    message = geometry_input_diagnostic(
        r"D:\calc\DOSCAR", r"D:\calc\vasprun.xml"
    )

    assert message is not None
    assert "DOSCAR" in message
    assert "vasprun.xml" in message
    assert "same" in message.lower()


def test_geometry_accepts_the_same_vasprun_path_case_insensitively():
    """Windows paths differ in case without referring to different files."""
    from core.services.hybridization_worker import geometry_input_diagnostic

    assert geometry_input_diagnostic(
        r"D:\Calc\vasprun.xml", r"d:\calc\VASPRUN.XML"
    ) is None


def test_geometry_rejection_reports_both_different_vasprun_paths():
    """Two XML files cannot provide one shared geometry and must be identified."""
    from core.services.hybridization_worker import geometry_input_diagnostic

    message = geometry_input_diagnostic(
        r"D:\calc-a\vasprun.xml", r"D:\calc-b\vasprun.xml"
    )

    assert message is not None
    assert "calc-a" in message
    assert "calc-b" in message


def test_hybridization_worker_emits_parse_and_render_progress():
    """Long XML tasks must expose observable phases instead of a frozen UI."""
    from core.services.hybridization_worker import HybridizationWorker

    params = ("source", "synthetic.xml", "1", ["dxy"], "total", "Fragment")
    worker = HybridizationWorker(params, params, geom_params=None)
    worker._parse_with_cache = lambda _params: (
        np.array([-1.0, 1.0]), {"dxy": np.ones(2)}, None, ["dxy"], "Fragment"
    )
    phases = []
    worker.progress.connect(phases.append)

    worker.run()

    assert any("Parsing" in phase for phase in phases)
    assert any("Rendering" in phase for phase in phases)


def test_lm_total_request_expands_to_real_components():
    from core.orbital_selection import resolve_orbital_request
    from core.pdos_metadata import PDOSCapabilities

    caps = PDOSCapabilities(
        source_format="DOSCAR", vasp_version=None, spin_mode="nonspin",
        orbital_resolution="lm",
        available_orbitals=("s", "py", "pz", "px", "dxy", "dyz", "dz2", "dxz", "dx2-y2"),
        structure_available=False, atom_selection_modes=("index",),
        field_source="doscar_layout", warnings=())

    request = resolve_orbital_request(["d"], caps)
    assert request.parser_orbitals == ("dxy", "dyz", "dz2", "dxz", "dx2-y2")
    assert request.output_components["d"] == request.parser_orbitals


def test_total_and_component_requests_share_parser_channels_without_duplication():
    from core.orbital_selection import resolve_orbital_request
    from core.pdos_metadata import PDOSCapabilities

    caps = PDOSCapabilities(
        source_format="DOSCAR", vasp_version=None, spin_mode="nonspin",
        orbital_resolution="lm",
        available_orbitals=("py", "pz", "px"),
        structure_available=False, atom_selection_modes=("index",),
        field_source="doscar_layout", warnings=())

    request = resolve_orbital_request(["p", "py"], caps)

    assert request.parser_orbitals == ("py", "pz", "px")
    assert request.output_components["p"] == ("py", "pz", "px")
    assert request.output_components["py"] == ("py",)


def test_hybridization_aggregate_does_not_double_count_selected_total_children():
    from core.orbital_selection import non_overlapping_orbitals

    assert non_overlapping_orbitals(["p", "py", "px", "dxy"]) == ("p", "dxy")


def test_unavailable_orbital_request_is_rejected_instead_of_zero_filled():
    from core.exceptions import OrbitalUnavailableError
    from core.orbital_selection import resolve_orbital_request
    from core.pdos_metadata import PDOSCapabilities

    caps = PDOSCapabilities(
        source_format="DOSCAR", vasp_version=None, spin_mode="nonspin",
        orbital_resolution="l", available_orbitals=("s", "p", "d", "f"),
        structure_available=False, atom_selection_modes=("index",),
        field_source="doscar_layout", warnings=())
    with pytest.raises(OrbitalUnavailableError):
        resolve_orbital_request(["dxy"], caps)


def test_fragment_panel_disables_unavailable_suborbitals(qapp):
    from models.app_state import AppState
    from ui.hybridization_win import FragmentPanel

    state = AppState()
    state.file_entries = [{
        "label": "LORBIT10", "path": r"D:\calc\DOSCAR",
        "capabilities": {
            "orbital_resolution": "l", "available_orbitals": ("s", "p", "d", "f"),
            "spin_mode": "nonspin", "source_format": "DOSCAR",
        }, "inspection_error": "",
    }]
    panel = FragmentPanel("Fragment", state)
    panel.refresh_sources()

    assert panel._orbital_checks["d"].isEnabled()
    assert not panel._orbital_checks["dxy"].isEnabled()
    assert "unavailable" in panel._orbital_checks["dxy"].toolTip().lower()


def test_fragment_panel_allows_total_and_components_together(qapp):
    from models.app_state import AppState
    from ui.hybridization_win import FragmentPanel

    panel = FragmentPanel("Fragment", AppState())
    panel._orbital_checks["d"].setChecked(True)
    panel._orbital_checks["dxy"].setChecked(True)

    assert panel._orbital_checks["d"].isChecked()
    assert panel._orbital_checks["dxy"].isChecked()
    assert panel.get_selected_orbitals()[:2] == ["d", "dxy"]


def test_hybridization_worker_caches_materialized_lm_total(monkeypatch):
    from core.pdos_metadata import PDOSCapabilities
    from core.services.hybridization_worker import HybridizationWorker

    caps = PDOSCapabilities(
        source_format="DOSCAR", vasp_version=None, spin_mode="nonspin",
        orbital_resolution="lm",
        available_orbitals=("dxy", "dyz", "dz2", "dxz", "dx2-y2"),
        structure_available=False, atom_selection_modes=("index",),
        field_source="doscar_layout", warnings=())
    calls = []
    components = {
        name: np.full(2, index + 1.0)
        for index, name in enumerate(caps.available_orbitals)
    }
    monkeypatch.setattr(
        "core.services.hybridization_worker.DataLoader.inspect", lambda _fp: caps)
    monkeypatch.setattr(
        "core.services.hybridization_worker.DataLoader.load_spin_all",
        lambda fp, atoms, orbitals=None: (
            calls.append(tuple(orbitals)) or np.array([-1.0, 1.0]),
            components, {name: np.zeros(2) for name in components}, components, 0.0))

    worker = HybridizationWorker.__new__(HybridizationWorker)
    worker._local_cache = {}
    worker._shared_cache = None
    params = ("sample", "missing-DOSCAR", "1", ["d"], "total", "sample")
    first = worker._parse_with_cache(params)
    second = worker._parse_with_cache(params)

    np.testing.assert_allclose(first[1]["d"], [15.0, 15.0])
    np.testing.assert_allclose(second[1]["d"], [15.0, 15.0])
    assert len(calls) == 1


def test_hybridization_worker_refreshes_alias_on_numeric_cache_hit(monkeypatch):
    from core.pdos_metadata import PDOSCapabilities
    from core.services.hybridization_worker import HybridizationWorker

    caps = PDOSCapabilities(
        source_format="DOSCAR", vasp_version=None, spin_mode="nonspin",
        orbital_resolution="lm", available_orbitals=("dxy",),
        structure_available=False, atom_selection_modes=("index",),
        field_source="doscar_layout", warnings=())
    calls = []
    density = {"dxy": np.ones(2)}
    monkeypatch.setattr(
        "core.services.hybridization_worker.DataLoader.inspect", lambda _fp: caps)
    monkeypatch.setattr(
        "core.services.hybridization_worker.DataLoader.load_spin_all",
        lambda fp, atoms, orbitals=None: (
            calls.append(atoms) or np.array([-1.0, 1.0]),
            density, {"dxy": np.zeros(2)}, density, 0.0))

    worker = HybridizationWorker.__new__(HybridizationWorker)
    worker._local_cache = {}
    worker._shared_cache = None
    first = worker._parse_with_cache(
        ("sample", "missing-DOSCAR", "70", ["dxy"], "total", "N"))
    second = worker._parse_with_cache(
        ("sample", "missing-DOSCAR", "70", ["dxy"], "total", "N67"))

    assert first[4] == "N"
    assert second[4] == "N67"
    assert calls == ["70"]


def test_fragment_source_change_emits_an_input_changed_signal(qapp):
    """Changing DOSCAR to vasprun.xml must invalidate an old hybridization plot."""
    from models.app_state import AppState
    from ui.hybridization_win import FragmentPanel

    state = AppState()
    state.file_entries = [
        {"label": "DOSCAR", "path": r"D:\calc\DOSCAR"},
        {"label": "vasprun.xml", "path": r"D:\calc\vasprun.xml"},
    ]
    panel = FragmentPanel("Fragment", state)
    panel.refresh_sources()
    changes = []
    panel.input_changed.connect(lambda: changes.append(True))

    panel.combo_file.setCurrentIndex(1)

    assert changes == [True]


def test_fragment_alias_change_invalidates_old_plot_identity(qapp):
    from models.app_state import AppState
    from ui.hybridization_win import FragmentPanel

    panel = FragmentPanel("Fragment", AppState())
    changes = []
    panel.input_changed.connect(lambda: changes.append(True))

    panel.entry_alias.setText("N67")

    assert changes == [True]


def test_hybridization_window_discards_cached_plot_when_source_changes(qapp):
    """A source mutation must not allow method/style changes to redraw old DOS."""
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow

    state = AppState()
    state.file_entries = [
        {"label": "DOSCAR", "path": r"D:\calc\DOSCAR"},
        {"label": "vasprun.xml", "path": r"D:\calc\vasprun.xml"},
    ]
    window = HybridizationWindow(state)
    window._has_plot_data = True
    window._cached_data = (object(), object())

    window.frag1.combo_file.setCurrentIndex(1)

    assert window._has_plot_data is False
    assert window._cached_data is None
    window.close()


def test_hybridization_window_clears_visible_stale_plot_when_source_changes(qapp):
    """The old DOS curve must disappear as soon as its source stops matching."""
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow

    state = AppState()
    state.file_entries = [
        {"label": "DOSCAR", "path": r"D:\calc\DOSCAR"},
        {"label": "vasprun.xml", "path": r"D:\calc\vasprun.xml"},
    ]
    window = HybridizationWindow(state)
    window._ax_top.plot([0.0, 1.0], [0.0, 1.0])
    window._has_plot_data = True
    window._cached_data = (object(), object())

    window.frag1.combo_file.setCurrentIndex(1)

    assert not window._ax_top.lines
    assert "input changed" in window.statusBar().currentMessage().lower()
    window.close()


def test_distance_table_handles_a_task_without_geometry_request(qapp):
    """A DOS-only task must not crash while updating the geometry table."""
    from core.services.hybridization_worker import GeometryAnalysisResult
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow

    window = HybridizationWindow(AppState())
    window._update_distance_table(GeometryAnalysisResult(None))

    assert window.table_dist.rowCount() == 1
    assert "not requested" in window.table_dist.item(0, 0).text().lower()
    window.close()


def test_hybridization_discards_a_completed_stale_worker_callback(qapp):
    """Changing input while parsing must prevent the old DOS from returning."""
    from core.services.hybridization_worker import GeometryAnalysisResult
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow

    window = HybridizationWindow(AppState())
    window._request_token = 4
    window._worker = SimpleNamespace(request_token=3)

    window._on_data_ready(object(), object(), GeometryAnalysisResult(None))

    assert window._has_plot_data is False
    assert window._cached_data is None
    window.close()


def _single_orbital_plot_data(label, orbital):
    energy = np.array([-1.0, 0.0, 1.0])
    density = {orbital: np.array([0.25, 1.0, 0.25])}
    return energy, density, None, [orbital], label


def test_global_center_control_updates_all_three_panels(qapp):
    from PySide6.QtCore import Qt
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow

    window = HybridizationWindow(AppState())
    window.chk_centers_all.setCheckState(Qt.Unchecked)

    assert not window.chk_center_top.isChecked()
    assert not window.chk_center_mid.isChecked()
    assert not window.chk_center_bot.isChecked()

    window.chk_center_mid.setChecked(True)
    assert window.chk_centers_all.checkState() == Qt.PartiallyChecked
    window.close()


def test_fragment_panels_draw_total_and_component_without_double_counting_overlap(qapp):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow

    energy = np.array([-1.0, 0.0, 1.0])
    d_total = np.array([2.0, 4.0, 2.0])
    dxy = np.array([0.5, 1.0, 0.5])
    window = HybridizationWindow(AppState())
    window._render_plot(
        (energy, {"d": d_total, "dxy": dxy}, None, ["d", "dxy"], "Mo"),
        _single_orbital_plot_data("N", "p"),
    )

    legend_labels = {text.get_text() for text in window._ax_mid.get_legend().texts}
    assert {"d-total", "dxy"} <= legend_labels
    np.testing.assert_allclose(window._ax_top.lines[0].get_ydata(), d_total)
    assert "Mo (d)" in window._ax_top.get_legend().texts[0].get_text()
    window.close()


def test_alias_and_actual_atom_selection_are_synchronized_across_plot(qapp):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow

    window = HybridizationWindow(AppState())
    window.frag1.entry_atoms.setText("12")
    window.frag2.entry_atoms.setText("70")
    window._render_plot(
        _single_orbital_plot_data("Mo", "d"),
        _single_orbital_plot_data("N67", "p"),
    )

    expected = "N67 [Atoms: 70]"
    assert expected in window.fig._suptitle.get_text()
    assert expected in window._ax_top.get_legend().texts[1].get_text()
    assert expected in window._ax_bot.get_title(loc="left")
    assert any(expected in text.get_text() for text in window._ax_bot.texts)
    assert window._plot_label2 == expected
    window.close()


def test_overlap_center_annotations_use_distinct_vertical_levels(qapp):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow

    energy = np.array([-2.0, -1.0, 0.0, 1.0])
    first = {"d": np.array([0.0, 1.0, 1.0, 0.0])}
    second = {"p": np.array([0.0, 0.8, 1.0, 0.0])}
    window = HybridizationWindow(AppState())
    window._render_plot(
        (energy, first, None, ["d"], "Mo"),
        (energy, second, None, ["p"], "N"),
    )

    center_texts = [text for text in window._ax_top.texts if text.get_text().startswith("ε(")]
    assert len(center_texts) == 2
    assert center_texts[0].get_position()[1] != center_texts[1].get_position()[1]
    window.close()


def test_overlap_theme_preserves_independent_fragment_themes(qapp):
    """Overlap changes must preserve independently selected fragment themes."""
    from matplotlib.colors import to_hex
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow
    from utils.styling import THEMES_CONFIG

    window = HybridizationWindow(AppState())
    window._has_plot_data = True
    window._cached_data = (
        _single_orbital_plot_data("Mo", "d"),
        _single_orbital_plot_data("N", "p"),
    )

    window.combo_theme_mid.setCurrentText("Theme 3 (Baby Blue-Pink)")
    window.combo_theme_bot.setCurrentText("Theme 4 (Green-Rose)")
    window.combo_theme_top.setCurrentIndex(1)

    expected = THEMES_CONFIG["2_color"][window.combo_theme_top.currentText()]
    assert window.combo_theme_mid.currentText() == "Theme 3 (Baby Blue-Pink)"
    assert window.combo_theme_bot.currentText() == "Theme 4 (Green-Rose)"
    assert to_hex(window._ax_top.lines[0].get_color()) == expected[0]
    assert to_hex(window._ax_top.lines[1].get_color()) == expected[1]
    assert to_hex(window._ax_mid.lines[0].get_color()) == expected[0]
    assert to_hex(window._ax_bot.lines[0].get_color()) == expected[1]
    window.close()


def test_fragment_theme_does_not_recolor_overlap_curve(qapp):
    """Fragment palettes cannot silently change the overlap palette."""
    from matplotlib.colors import to_hex
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow
    from utils.styling import THEMES_CONFIG

    window = HybridizationWindow(AppState())
    window._has_plot_data = True
    window._cached_data = (
        _single_orbital_plot_data("Mo", "d"),
        _single_orbital_plot_data("N", "p"),
    )

    window.combo_theme_bot.setCurrentText("Theme 4 (Green-Rose)")

    expected = THEMES_CONFIG["2_color"]["Theme 1 (Red-Gray)"][1]
    assert to_hex(window._ax_top.lines[1].get_color()) == expected
    assert to_hex(window._ax_bot.lines[0].get_color()) == expected
    window.close()


def test_main_calculation_status_identifies_the_selected_quadrature():
    """The UI must expose which numerical method produced displayed numbers."""
    from ui.main_window import MainWindow

    message = MainWindow._calculation_status_text(1, 2, "simpson")

    assert "1/2" in message
    assert "Simpson" in message


def test_main_window_marks_results_stale_when_integration_method_changes(qapp):
    """A method change must not leave a previous trapezoid result looking current."""
    from ui.main_window import MainWindow

    window = MainWindow()
    window.param_panel.combo_method.setCurrentIndex(1)

    message = window.statusBar().currentMessage()
    assert "Simpson" in message
    assert "Run" in message
    window.close()


def test_main_window_states_honest_d_projection_semantics(qapp):
    from PySide6.QtWidgets import QLabel
    from ui.main_window import MainWindow

    window = MainWindow()
    labels = [label.text() for label in window.findChildren(QLabel)]
    semantic_text = " ".join(labels)
    assert "3d, 4d, or 5d" in semantic_text
    assert "VASP" in semantic_text
    window.close()


def test_main_window_title_exposes_running_version(qapp):
    from ui.main_window import MainWindow
    from utils.helpers import get_app_version

    window = MainWindow()
    assert f"v{get_app_version()}" in window.windowTitle()
    window.close()


def test_main_window_left_controls_scroll_instead_of_forcing_window_height(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QScrollArea
    from ui.main_window import MainWindow

    window = MainWindow()
    window.resize(1300, 850)
    window.show()
    qapp.processEvents()

    assert isinstance(window.left_scroll, QScrollArea)
    assert window.left_scroll.widgetResizable()
    assert window.left_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert window.minimumSizeHint().height() <= 850
    assert window.height() <= 850
    window.close()


def test_main_window_compact_controls_fit_their_text(qapp):
    from PySide6.QtWidgets import QAbstractButton, QComboBox
    from ui.main_window import MainWindow

    window = MainWindow()
    window.resize(1300, 850)
    window.show()
    qapp.processEvents()

    controls = [
        *window.left_panel.findChildren(QAbstractButton),
        *window.left_panel.findChildren(QComboBox),
    ]
    assert controls
    for control in controls:
        text = control.text() if isinstance(control, QAbstractButton) else control.currentText()
        if not text:
            continue
        text_width = control.fontMetrics().horizontalAdvance(text.replace("&", ""))
        extra_width = 30 if isinstance(control, QAbstractButton) else 44
        assert control.width() >= text_width + extra_width, (
            f"{type(control).__name__} text is clipped: {text!r}, "
            f"width={control.width()}, required={text_width + extra_width}"
        )
        assert control.height() >= control.fontMetrics().height() + 10, (
            f"{type(control).__name__} text is vertically clipped: {text!r}, "
            f"height={control.height()}"
        )
    window.close()


def test_orbital_colors_stay_stable_with_total_and_theme_changes(qapp):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow
    from core.parsers import d_orb_names
    window = HybridizationWindow(AppState())
    before = window._fragment_color_map(0)
    for orb in ["d", *d_orb_names]:
        window.frag1._orbital_checks[orb].setChecked(True)
    assert window._fragment_color_map(0) == before
    window.combo_theme_mid.setCurrentText("Distinct Categorical")
    window.frag1._orbital_checks["d"].setChecked(False)
    assert window.combo_theme_mid.currentText() == "Distinct Categorical"
    window._fragment_style(0)["colors"] = {"dxy": "#123456", "d": "#654321"}
    window.combo_theme_top.setCurrentIndex(1)
    window.combo_theme_mid.setCurrentText("Mountain Sunset")
    assert window._fragment_color_map(0)["dxy"] == "#123456"
    assert window._fragment_color_map(0)["d"] == "#654321"
    assert window._fragment_color_map(1)["dxy"] == before["dxy"]
    window.close()


def test_pdos_import_and_workspace_color_roundtrip(qapp, tmp_path):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow
    state = AppState()
    state.orb_colors["dxy"] = "#123456"
    window = HybridizationWindow(state)
    window._import_pdos_colors(1)
    window._set_total_fill(1, True)
    assert window._fragment_color_map(1)["dxy"] == "#123456"
    assert window._fragment_color_map(0)["dxy"] != "#123456"
    window.combo_theme_top.setCurrentIndex(2)
    path = tmp_path / "colors.json"
    state.save_workspace(str(path))
    loaded = AppState()
    loaded.load_workspace(str(path))
    restored = HybridizationWindow(loaded)
    assert restored._fragment_color_map(1) == window._fragment_color_map(1)
    assert restored._total_fill_1.isChecked()
    restored._reset_fragment_colors(1)
    assert restored._fragment_color_map(1)["dxy"] != "#123456"
    assert state.orb_colors["dxy"] == "#123456"
    window.close()
    restored.close()


def test_total_style_spin_colors_and_export(qapp, tmp_path):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow
    from matplotlib.colors import to_hex
    window = HybridizationWindow(AppState())
    e = np.array([-1., 0., 1.])
    up = {"d": np.array([2., 4., 2.]), "dxy": np.array([.5, 1., .5])}
    down = {k: v / 2 for k, v in up.items()}
    window._fragment_style(0)["colors"] = {"dxy": "#123456", "d": "#654321"}
    data = ((e, up, down, ["d", "dxy"], "Mo"), _single_orbital_plot_data("N", "p"))
    window._render_plot(*data)
    lines = window._ax_mid.lines
    assert [to_hex(line.get_color()) for line in lines[:4]] == ["#654321", "#654321", "#123456", "#123456"]
    assert lines[0].get_linewidth() > lines[2].get_linewidth()
    assert len(window._ax_mid.collections) == 2
    np.testing.assert_allclose(window._ax_top.lines[0].get_ydata(), up["d"])
    np.testing.assert_allclose(window._ax_top.lines[1].get_ydata(), -down["d"])
    path = tmp_path / "colors.svg"
    window.fig.savefig(path)
    svg = path.read_text(encoding="utf-8")
    assert "#123456" in svg and "#654321" in svg
    window._set_total_fill(0, True)
    window._render_plot(*data)
    assert len(window._ax_mid.collections) == 4
    window.close()
