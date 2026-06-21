# Bar Chart System Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users choose which calculated systems appear in the Comparison Bar Chart without changing existing chart styling or numerical data.

**Architecture:** `BarChartWidget` retains the complete `results_data` list and owns a checked-system selector in its existing toolbar. Rendering filters only a local display list by selected label, then executes the unchanged bar-chart drawing logic. The reusable checked combo from Multi-System PDOS supplies the interaction model.

**Tech Stack:** Python 3.12, PySide6, Matplotlib, pytest.

---

### Task 1: Add toolbar selector and preserve its selection model

**Files:**
- Modify: `ui/charts/bar_chart.py`
- Modify: `ui/charts/bar_chart_dialogs.py`
- Test: `tests/test_bar_chart_selector.py`

- [ ] **Step 1: Write failing tests for default and refreshed selection state**

```python
def test_bar_chart_selector_defaults_to_all_result_labels(qapp, results):
    chart = BarChartWidget()
    chart.update_chart(results)
    assert chart.data_dlg.combo_systems.get_checked_items() == ["A", "B"]


def test_bar_chart_selector_keeps_existing_choice_and_checks_new_labels(qapp, results):
    chart = BarChartWidget()
    chart.update_chart(results)
    chart.data_dlg.combo_systems.model().item(1, 0).setCheckState(Qt.Unchecked)
    chart.update_chart([*results, make_result("C")])
    assert chart.data_dlg.combo_systems.get_checked_items() == ["A", "C"]
```

- [ ] **Step 2: Run selector-state tests and verify they fail**

Run: `C:\Users\21483\.conda\envs\lis_sac_ml\python.exe -m pytest tests/test_bar_chart_selector.py -q`

Expected: FAIL because `BarChartWidget` has no `data_dlg` selector.

- [ ] **Step 3: Add a data dialog backed by the existing checked combo widget**

```python
from ui.charts.bar_chart_dialogs import BarChartDataDialog

self.data_dlg = BarChartDataDialog(self)
self.data_dlg.real_time_update.connect(self._trigger_update)
btn_data = QPushButton("📊 Data")
btn_data.clicked.connect(self.data_dlg.show)
toolbar_layout.insertWidget(0, btn_data)
```

Define `BarChartDataDialog` in `ui/charts/bar_chart_dialogs.py` with only `CheckableComboBox combo_systems`; route its `selection_changed` signal to `real_time_update`. Add `_sync_system_selector(results_data)` that deduplicates result labels in order, restores valid checked labels, and checks all labels on the first load plus labels that are new on later refreshes.

- [ ] **Step 4: Run selector-state tests and verify they pass**

Run: `C:\Users\21483\.conda\envs\lis_sac_ml\python.exe -m pytest tests/test_bar_chart_selector.py -q`

Expected: PASS.

### Task 2: Filter only the rendered bar-chart data

**Files:**
- Modify: `ui/charts/bar_chart.py`
- Test: `tests/test_bar_chart_selector.py`

- [ ] **Step 1: Write failing tests for filtering and empty selection**

```python
def test_bar_chart_filters_rows_to_checked_systems(qapp, results):
    chart = BarChartWidget()
    chart.update_chart(results)
    chart.data_dlg.combo_systems.model().item(1, 0).setCheckState(Qt.Unchecked)
    chart.update_chart(results)
    assert chart._rendered_labels == ["A"]


def test_bar_chart_safely_clears_when_no_system_is_checked(qapp, results):
    chart = BarChartWidget()
    chart.update_chart(results)
    chart.data_dlg.combo_systems.model().item(0, 0).setCheckState(Qt.Unchecked)
    chart.data_dlg.combo_systems.model().item(1, 0).setCheckState(Qt.Unchecked)
    chart.update_chart(results)
    assert not chart.fig.axes
```

- [ ] **Step 2: Run filtering tests and verify they fail**

Run: `C:\Users\21483\.conda\envs\lis_sac_ml\python.exe -m pytest tests/test_bar_chart_selector.py -q`

Expected: FAIL because the rendering path still consumes every result label.

- [ ] **Step 3: Filter the local render list before existing plotting code**

```python
self._current_data = list(results_data or [])
selected = set(self.data_dlg.combo_systems.get_checked_items())
render_data = [row for row in self._current_data if row.label in selected]
self._rendered_labels = list(dict.fromkeys(row.label for row in render_data))
self.fig.clear()
if not render_data:
    self.canvas.draw()
    return
```

Use `render_data` for existing label/range discovery and bar drawing. Keep `_current_data` complete so future checkbox changes can redraw without losing unselected rows.

- [ ] **Step 4: Run filtering tests and verify they pass**

Run: `C:\Users\21483\.conda\envs\lis_sac_ml\python.exe -m pytest tests/test_bar_chart_selector.py -q`

Expected: PASS.

### Task 3: Run compatibility verification and commit

**Files:**
- Modify: `ui/charts/bar_chart.py`
- Create: `tests/test_bar_chart_selector.py`

- [ ] **Step 1: Run full regression suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; C:\Users\21483\.conda\envs\lis_sac_ml\python.exe -m pytest -q`

Expected: all existing tests plus bar-chart selector tests pass.

- [ ] **Step 2: Check whitespace and working-tree scope**

Run: `git diff --check; git status --short`

Expected: only `ui/charts/bar_chart.py` and `tests/test_bar_chart_selector.py` are modified or added.

- [ ] **Step 3: Commit the feature**

```powershell
git add ui/charts/bar_chart.py tests/test_bar_chart_selector.py
git commit -m "feat: select systems in comparison bar chart"
```
