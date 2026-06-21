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
