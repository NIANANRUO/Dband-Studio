"""Regression tests for persistent and batch image export."""

from pathlib import Path

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _cache(scale=1.0):
    energy = np.array([-1.0, 0.0, 1.0])
    return {
        "energy": energy,
        "ef": 0.0,
        "up": {"d": np.array([0.25, 1.0, 0.25]) * scale},
        "down": None,
        "has_spin": False,
    }


def test_default_export_directory_prefers_remembered_location(tmp_path):
    from utils.export_paths import default_export_directory

    remembered = tmp_path / "my exports"
    chosen = default_export_directory(
        [{"path": str(tmp_path / "source" / "DOSCAR")}],
        stored_directory=str(remembered),
        documents_directory=str(tmp_path / "Documents"),
    )

    assert chosen == remembered


def test_default_export_directory_uses_shared_source_parent(tmp_path):
    from utils.export_paths import default_export_directory

    source = tmp_path / "calculation"
    chosen = default_export_directory([
        {"path": str(source / "DOSCAR")},
        {"path": str(source / "vasprun.xml")},
    ], documents_directory=str(tmp_path / "Documents"))

    assert chosen == source / "DBandStudio_Export"


def test_default_export_directory_uses_documents_for_mixed_sources(tmp_path):
    from utils.export_paths import default_export_directory

    chosen = default_export_directory([
        {"path": str(tmp_path / "a" / "DOSCAR")},
        {"path": str(tmp_path / "b" / "DOSCAR")},
    ], documents_directory=str(tmp_path / "Documents"))

    assert chosen == tmp_path / "Documents" / "DBand Studio" / "Exports"


def test_export_filename_is_safe_and_never_overwritten(tmp_path):
    from core.services.exporter import (
        available_export_path, safe_export_stem, selected_export_path,
    )

    assert safe_export_stem('Mo:site/A*') == "Mo_site_A_"
    assert safe_export_stem("CON") == "_CON"

    first = available_export_path(tmp_path, "Mo/site", ".png")
    first.touch()
    second = available_export_path(tmp_path, "Mo/site", ".png")

    assert first.name == "Mo_site.png"
    assert second.name == "Mo_site_2.png"
    assert selected_export_path(tmp_path / "figure", "pdf").name == "figure.pdf"
    assert selected_export_path(tmp_path / "figure.notes", "svg").name == "figure.notes.svg"


def test_batch_export_writes_every_system_and_restores_current_view(qapp, tmp_path):
    from models.app_state import AppState
    from ui.main_window import MainWindow
    from ui.widgets.image_export_dialog import ImageExportOptions

    window = MainWindow()
    window.state = AppState()
    window.state.parsed_cache["Original"] = _cache()
    window.state.parsed_cache["Second/System"] = _cache(2.0)
    window.pdos_chart.draw_pdos(
        "Original", window.state.parsed_cache["Original"])
    window.pdos_chart.style_dlg.spin_lw.setValue(2.5)
    window.pdos_chart.axes_config = {
        "x_min": -0.5, "x_max": 0.5, "y_min": None, "y_max": None,
    }

    options = ImageExportOptions(
        output_directory=tmp_path,
        image_format="png",
        dpi=72,
        system_labels=("Original", "Second/System"),
        include_individual_pdos=True,
        include_bar_chart=False,
        include_multi_pdos=False,
    )
    result = window._export_batch_images(options)

    assert not result.failures
    assert len(result.exported) == 2
    assert all(Path(path).exists() for path in result.exported)
    assert {Path(path).name for path in result.exported} == {
        "Original_PDOS.png", "Second_System_PDOS.png",
    }
    assert window.pdos_chart._current_label == "Original"
    assert window.pdos_chart._axes[0].get_xlim() == pytest.approx((-0.5, 0.5))
    assert window.pdos_chart._axes[0].lines[0].get_linewidth() == pytest.approx(2.5)
    window.close()
