"""Runtime language switching must not alter analytical control values."""

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def english_after_test(qapp):
    from ui.i18n import get_language_manager

    manager = get_language_manager()
    manager.install(qapp)
    manager.set_language("en", persist=False)
    yield manager
    manager.set_language("en", persist=False)


def _cache():
    return {
        "energy": np.array([-1.0, 0.0, 1.0]),
        "ef": 0.0,
        "up": {"d": np.array([0.25, 1.0, 0.25])},
        "down": None,
        "has_spin": False,
    }


def test_main_window_switches_both_directions_with_stable_combo_values(
        qapp, english_after_test):
    from ui.i18n import combo_value
    from ui.main_window import MainWindow

    window = MainWindow()
    assert window.btn_run.text() == "▶  Run Calculation"
    assert combo_value(window.file_panel.combo_type) == "Auto Detect"

    english_after_test.set_language("zh_CN", persist=False)
    qapp.processEvents()

    assert window.btn_run.text() == "▶  运行计算"
    assert window.tabs.tabText(0) == "对比柱状图"
    assert window.file_panel.combo_type.currentText() == "自动检测"
    assert combo_value(window.file_panel.combo_type) == "Auto Detect"
    assert window.file_panel.get_file_type() == "Auto Detect"
    assert window.btn_language.text() == "EN"

    english_after_test.set_language("en", persist=False)
    qapp.processEvents()

    assert window.btn_run.text() == "▶  Run Calculation"
    assert window.tabs.tabText(0) == "Comparison Bar Chart"
    assert window.file_panel.combo_type.currentText() == "Auto Detect"
    assert window.btn_language.text() == "中文"
    window.close()


def test_language_switch_redraws_pdos_without_changing_curve_data(
        qapp, english_after_test):
    from ui.main_window import MainWindow

    window = MainWindow()
    window.pdos_chart.draw_pdos("Mo", _cache())
    before = window.pdos_chart._axes[0].lines[0]
    before_x = before.get_xdata().copy()
    before_y = before.get_ydata().copy()
    before_color = before.get_color()

    english_after_test.set_language("zh_CN", persist=False)
    qapp.processEvents()

    after = window.pdos_chart._axes[0].lines[0]
    np.testing.assert_allclose(after.get_xdata(), before_x)
    np.testing.assert_allclose(after.get_ydata(), before_y)
    assert after.get_color() == before_color
    assert after.axes._left_title.get_text() == "Mo 总 PDOS"
    window.close()


def test_hybridization_window_inherits_language_and_keeps_internal_values(
        qapp, english_after_test):
    from models.app_state import AppState
    from ui.hybridization_win import HybridizationWindow
    from ui.i18n import combo_value

    english_after_test.set_language("zh_CN", persist=False)
    window = HybridizationWindow(AppState())
    english_after_test.apply(window)

    assert window.windowTitle() == "轨道杂化分析（异步）"
    assert window.left_tabs.tabText(0) == "片段 1"
    assert window.combo_spin.currentText() == "总计"
    assert combo_value(window.combo_spin) == "Total"
    assert window.combo_integ_range.currentText() == "全部"
    assert combo_value(window.combo_integ_range) == "All"
    window.close()


def test_documentation_dialog_is_localized_when_created_after_switch(
        qapp, english_after_test):
    from PySide6.QtWidgets import QLabel
    from ui.help_dialogs import DocumentationDialog

    english_after_test.set_language("zh_CN", persist=False)
    dialog = DocumentationDialog()
    english_after_test.apply(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert dialog.windowTitle() == "DBand Studio 使用说明"
    assert "DBand Studio 用户指南" in labels
    assert any("目标原子" in text and "积分范围" in text for text in labels)
    dialog.close()
