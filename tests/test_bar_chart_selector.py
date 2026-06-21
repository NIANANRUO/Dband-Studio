import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from models.results import DbandResult
from ui.charts.bar_chart import BarChartWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def make_result(label, range_name="All", center=-1.0):
    return DbandResult(
        label=label,
        range_name=range_name,
        center=center,
        width=1.0,
        filling=50.0,
    )


@pytest.fixture
def results():
    return [make_result("A", center=-1.0), make_result("B", center=-2.0)]


def test_bar_chart_selector_defaults_to_all_result_labels(qapp, results):
    chart = BarChartWidget()
    chart.update_chart(results)

    assert chart.data_dlg.combo_systems.get_checked_items() == ["A", "B"]
    chart.close()


def test_bar_chart_selector_keeps_existing_choice_and_checks_new_labels(qapp, results):
    chart = BarChartWidget()
    chart.update_chart(results)
    chart.data_dlg.combo_systems.model().item(1, 0).setCheckState(Qt.Unchecked)
    chart.update_chart([*results, make_result("C", center=-3.0)])

    assert chart.data_dlg.combo_systems.get_checked_items() == ["A", "C"]
    chart.close()


def test_bar_chart_filters_rows_to_checked_systems(qapp, results):
    chart = BarChartWidget()
    chart.update_chart(results)
    chart.data_dlg.combo_systems.model().item(1, 0).setCheckState(Qt.Unchecked)
    chart.update_chart(results)

    assert chart._rendered_labels == ["A"]
    chart.close()


def test_bar_chart_safely_clears_when_no_system_is_checked(qapp, results):
    chart = BarChartWidget()
    chart.update_chart(results)
    chart.data_dlg.combo_systems.model().item(0, 0).setCheckState(Qt.Unchecked)
    chart.data_dlg.combo_systems.model().item(1, 0).setCheckState(Qt.Unchecked)
    chart.update_chart(results)

    assert not chart.fig.axes
    chart.close()


def test_bar_chart_selection_does_not_reset_existing_style_controls(qapp, results):
    chart = BarChartWidget()
    chart.update_chart(results)
    chart.labels_dlg.spin_xtick_fs.setValue(13)
    chart.data_dlg.combo_systems.model().item(1, 0).setCheckState(Qt.Unchecked)
    chart.update_chart(results)

    assert chart.labels_dlg.spin_xtick_fs.value() == 13
    chart.close()
