"""
Main application window - assembles all UI components and orchestrates computation.
"""
from pathlib import Path

import numpy as np

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QProgressDialog,
    QPushButton, QSplitter, QMessageBox, QFileDialog, QGroupBox, QTabWidget,
    QMenuBar, QMenu, QFrame, QLabel, QStackedWidget, QScrollArea, QApplication,
    QDialog,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QAction, QDesktopServices
from ui.theme_macos import LIGHT_GLASS_QSS, DARK_GLASS_QSS
from ui.help_dialogs import DocumentationDialog, AboutDialog

from models.app_state import AppState
from core.services.calculation_worker import CalculationWorker
from core.services.exporter import (
    BatchImageExportResult, DataExporter, available_export_path,
    selected_export_path,
)
from core.exceptions import (
    DbandError, MissingProjectedDOSError, AtomNotFoundError,
    FileTypeError, OrbitalMissingError, VASPKitAtomError,
    AmbiguousLayoutError, FileIntegrityError, OrbitalUnavailableError,
    AtomSelectionError, StructureMismatchError, UnsupportedLayoutError,
)
from ui.panels.file_manager import FileManagerPanel
from ui.panels.param_manager import ParamManagerPanel
from ui.panels.results_table import ResultsTableWidget
from ui.charts.bar_chart import BarChartWidget
from ui.charts.pdos_chart import PDOSChartWidget
from ui.charts.multi_pdos_chart import MultiPDOSChartWidget
from utils.styling import BTN_RUN_COLOR, BTN_HYB_COLOR
from utils.helpers import get_app_version
from ui.control_sizing import ensure_compact_controls_fit_text
from ui.widgets.image_export_dialog import ImageExportDialog, ImageExportOptions
from ui.i18n import get_language_manager, localized_stylesheet, tr
from utils.export_paths import (
    ensure_export_directory, get_export_directory, remember_export_directory,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"DBand Studio v{get_app_version()}")
        self.resize(1300, 850)
        self.setAcceptDrops(True)
        
        self.language_manager = get_language_manager()
        self.language_manager.install(QApplication.instance())
        self.is_dark_mode = False
        self.setStyleSheet(localized_stylesheet(LIGHT_GLASS_QSS))

        self.state = AppState()
        self._build_ui()
        self._build_menu()
        self._connect_signals()
        self.language_manager.language_changed.connect(self._on_language_changed)
        self.language_manager.apply(self)
        self._update_language_button()
        self.statusBar().showMessage(tr("Ready — drag files here or click Add Files."))

    def showEvent(self, event):
        super().showEvent(event)
        # Font metrics can change when the window enters a high-DPI screen.
        ensure_compact_controls_fit_text(self.left_panel)
        self.left_panel.layout().activate()

    def _update_language_button(self):
        is_chinese = self.language_manager.language == "zh_CN"
        self.btn_language.setText("EN" if is_chinese else "中文")
        self.btn_language.setToolTip(
            "Switch to English" if is_chinese else "切换为中文")

    def _on_language_changed(self, _language):
        """Refresh visible text and plots without changing analytical state."""
        base_qss = DARK_GLASS_QSS if self.is_dark_mode else LIGHT_GLASS_QSS
        self.setStyleSheet(localized_stylesheet(base_qss))
        self.language_manager.apply(self)
        self._update_language_button()
        if self.bar_chart._current_data is not None:
            self.bar_chart.update_chart(self.bar_chart._current_data)
        if self.pdos_chart._current_label and self.pdos_chart._current_cache:
            self.pdos_chart._on_redraw_request()
        if self.multi_pdos_chart._parsed_cache:
            self.multi_pdos_chart.draw_plot()
        if hasattr(self, "_hyb_win") and self._hyb_win:
            self._hyb_win.set_dark_mode(self.is_dark_mode)
            self.language_manager.apply(self._hyb_win)
            if self._hyb_win._cached_data:
                self._hyb_win._render_plot(*self._hyb_win._cached_data)
        ensure_compact_controls_fit_text(self.left_panel)

    # ---------- drag & drop ----------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        self.file_panel.import_paths(paths)

    # ---------- UI construction ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # ---- LEFT PANEL ----
        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(380)
        ll = QVBoxLayout(self.left_panel)
        ll.setContentsMargins(4, 4, 4, 4)

        self.file_panel = FileManagerPanel(self.state)
        ll.addWidget(self.file_panel)

        self.param_panel = ParamManagerPanel(self.state)
        ll.addWidget(self.param_panel)

        projection_note = QLabel(
            "d-band metrics use the VASP d projection. Standard vasprun.xml "
            "and DOSCAR data cannot independently select 3d, 4d, or 5d.")
        projection_note.setObjectName("ProjectionSemanticsNote")
        projection_note.setWordWrap(True)
        projection_note.setStyleSheet("font-size: 10px; color: #666666; padding: 2px 8px;")
        ll.addWidget(projection_note)

        # Actions
        g3 = QFrame()
        g3.setObjectName("LeftCard")
        l3 = QVBoxLayout(g3)

        heading_row = QHBoxLayout()
        heading_row.addStretch()
        lbl3 = QLabel("3. Actions")
        lbl3.setAlignment(Qt.AlignCenter)
        lbl3.setStyleSheet("font-weight: bold; font-size: 13px; color: #333333;")
        heading_row.addWidget(lbl3)
        heading_row.addStretch()
        self.btn_language = QPushButton("中文")
        self.btn_language.setProperty("_i18n_skip", True)
        self.btn_language.setFixedWidth(54)
        self.btn_language.setToolTip("切换为中文 / Switch to English")
        self.btn_language.clicked.connect(self.language_manager.toggle)
        heading_row.addWidget(self.btn_language)
        l3.addLayout(heading_row)

        self.btn_run = QPushButton("\u25b6  Run Calculation")
        self.btn_run.setFixedHeight(40)
        self.btn_run.setProperty("isPrimary", "true")
        self.btn_run.clicked.connect(self.run_calculation)
        l3.addWidget(self.btn_run)

        erow = QHBoxLayout()
        btn_csv = QPushButton("Export CSV")
        btn_csv.clicked.connect(self.export_csv)
        erow.addWidget(btn_csv)
        btn_images = QPushButton("Export Images ▾")
        image_menu = QMenu(btn_images)
        image_menu.addAction("Save Current Image...", self.save_chart)
        image_menu.addAction("Batch Export Images...", self.batch_export_images)
        btn_images.setMenu(image_menu)
        erow.addWidget(btn_images)
        l3.addLayout(erow)

        # Hybridization button
        btn_hyb = QPushButton("\u269b Orbital Hybridization Analysis")
        btn_hyb.setFixedHeight(36)
        btn_hyb.setProperty("isPrimary", "true")
        btn_hyb.clicked.connect(self._open_hybridization)
        l3.addWidget(btn_hyb)

        ll.addWidget(g3)
        ll.addStretch()

        self.left_scroll = QScrollArea()
        self.left_scroll.setObjectName("LeftControlScroll")
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.left_scroll.setFrameShape(QFrame.NoFrame)
        self.left_scroll.setFixedWidth(410)
        self.left_scroll.setWidget(self.left_panel)
        self.left_panel.ensurePolished()
        ensure_compact_controls_fit_text(self.left_panel)

        # ---- RIGHT PANEL ----
        right = QSplitter(Qt.Vertical)

        self.results_table = ResultsTableWidget(self.state.orb_colors)
        right.addWidget(self.results_table)

        # Chart tabs
        chart_panel = QWidget()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()

        self.bar_chart = BarChartWidget()
        self.tabs.addTab(self.bar_chart, "Comparison Bar Chart")

        self.pdos_chart = PDOSChartWidget(self.state.orb_colors)
        self.tabs.addTab(self.pdos_chart, "PDOS Curves")

        self.multi_pdos_chart = MultiPDOSChartWidget()
        self.tabs.addTab(self.multi_pdos_chart, "Multi-System PDOS")

        chart_layout.addWidget(self.tabs)
        
        # Use a QStackedWidget to hold the toolbar_widget for all three charts
        self.corner_stack = QStackedWidget()
        self.corner_stack.addWidget(self.bar_chart.toolbar_widget)
        self.corner_stack.addWidget(self.pdos_chart.toolbar_widget)
        self.corner_stack.addWidget(self.multi_pdos_chart.toolbar_widget)
        
        # Place the StackedWidget in the top-right corner of the Main Tab Widget
        self.tabs.setCornerWidget(self.corner_stack, Qt.TopRightCorner)
        self.tabs.currentChanged.connect(self.corner_stack.setCurrentIndex)

        right.addWidget(chart_panel)
        right.setSizes([320, 420])

        root.addWidget(self.left_scroll)
        root.addWidget(right)

    # ---------- menu bar ----------
    def _build_menu(self):
        menubar = self.menuBar()

        # --- File Menu ---
        file_menu = menubar.addMenu("File")

        act_add_files = QAction("Add Files...", self)
        act_add_files.triggered.connect(self.file_panel.add_files)
        file_menu.addAction(act_add_files)

        act_add_folder = QAction("Add Folder...", self)
        act_add_folder.triggered.connect(self.file_panel.add_folder)
        file_menu.addAction(act_add_folder)

        file_menu.addSeparator()

        act_save_ws = QAction("Save Workspace...", self)
        act_save_ws.setShortcut("Ctrl+S")
        act_save_ws.triggered.connect(self._save_workspace)
        file_menu.addAction(act_save_ws)

        act_load_ws = QAction("Load Workspace...", self)
        act_load_ws.setShortcut("Ctrl+O")
        act_load_ws.triggered.connect(self._load_workspace)
        file_menu.addAction(act_load_ws)

        file_menu.addSeparator()

        act_export = QAction("Export CSV...", self)
        act_export.triggered.connect(self.export_csv)
        file_menu.addAction(act_export)

        act_save_chart = QAction("Save Current Image...", self)
        act_save_chart.triggered.connect(self.save_chart)
        file_menu.addAction(act_save_chart)

        act_batch_images = QAction("Batch Export Images...", self)
        act_batch_images.triggered.connect(self.batch_export_images)
        file_menu.addAction(act_batch_images)

        file_menu.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # --- Run Menu ---
        run_menu = menubar.addMenu("Run")

        act_clear_data = QAction("Clear All Data", self)
        act_clear_data.triggered.connect(self._on_clear_all)
        run_menu.addAction(act_clear_data)

        run_menu.addSeparator()

        act_run_calc = QAction("Run DBand Calculation", self)
        act_run_calc.setShortcut("Ctrl+R")
        act_run_calc.triggered.connect(self.run_calculation)
        run_menu.addAction(act_run_calc)

        act_run_hybrid = QAction("Orbital Hybridization Analysis", self)
        act_run_hybrid.triggered.connect(self._open_hybridization)
        run_menu.addAction(act_run_hybrid)

        # --- View Menu ---
        view_menu = menubar.addMenu("View")

        act_toggle_left = QAction("Toggle Left Control Panel", self)
        act_toggle_left.setShortcut("Ctrl+L")
        act_toggle_left.triggered.connect(self._toggle_left_panel)
        view_menu.addAction(act_toggle_left)

        act_toggle_table = QAction("Toggle Results Table", self)
        act_toggle_table.setShortcut("Ctrl+T")
        act_toggle_table.triggered.connect(self._toggle_results_table)
        view_menu.addAction(act_toggle_table)

        view_menu.addSeparator()

        act_open_data = QAction("Open Data/Labels Settings", self)
        act_open_data.setShortcut("Ctrl+D")
        act_open_data.triggered.connect(self._open_data_settings)
        view_menu.addAction(act_open_data)

        act_open_style = QAction("Open Style/Legend Settings", self)
        act_open_style.setShortcut("Ctrl+M")
        act_open_style.triggered.connect(self._open_style_settings)
        view_menu.addAction(act_open_style)

        act_open_pattern = QAction("Open Pattern Settings", self)
        act_open_pattern.setShortcut("Ctrl+P")
        act_open_pattern.triggered.connect(self._open_pattern_settings)
        view_menu.addAction(act_open_pattern)

        act_open_axes = QAction("Open Axes Settings", self)
        act_open_axes.setShortcut("Ctrl+E")
        act_open_axes.triggered.connect(self._open_axes_settings)
        view_menu.addAction(act_open_axes)

        view_menu.addSeparator()

        act_reset_view = QAction("Reset Chart View", self)
        act_reset_view.setShortcut("Ctrl+0")
        act_reset_view.triggered.connect(self._reset_chart_view)
        view_menu.addAction(act_reset_view)

        act_toggle_grid = QAction("Toggle Global Grid", self)
        act_toggle_grid.setShortcut("Ctrl+G")
        act_toggle_grid.triggered.connect(self._toggle_global_grid)
        view_menu.addAction(act_toggle_grid)

        view_menu.addSeparator()
        
        theme_menu = view_menu.addMenu("Theme")
        act_theme_light = QAction("Light Mode", self)
        act_theme_light.triggered.connect(lambda: self._apply_theme("light"))
        theme_menu.addAction(act_theme_light)
        
        act_theme_dark = QAction("Dark Mode", self)
        act_theme_dark.triggered.connect(lambda: self._apply_theme("dark"))
        theme_menu.addAction(act_theme_dark)

        # --- Help Menu ---
        help_menu = menubar.addMenu("Help")

        act_docs = QAction("Documentation", self)
        act_docs.triggered.connect(self._open_documentation)
        help_menu.addAction(act_docs)

        act_about = QAction("About DBand Studio", self)
        act_about.triggered.connect(self._open_about)
        help_menu.addAction(act_about)

    # ---------- view controls ----------
    def _apply_theme(self, mode):
        self.is_dark_mode = (mode == "dark")
        qss = DARK_GLASS_QSS if self.is_dark_mode else LIGHT_GLASS_QSS
        self.setStyleSheet(localized_stylesheet(qss))
        # Update charts and panels
        for w in [self.bar_chart, self.pdos_chart, self.multi_pdos_chart, 
                  self.file_panel, self.results_table]:
            if hasattr(w, "set_dark_mode"):
                w.set_dark_mode(self.is_dark_mode)
        if hasattr(self, '_hyb_win'):
            self._hyb_win.set_dark_mode(self.is_dark_mode)
            
    def _toggle_left_panel(self):
        self.left_panel.setVisible(not self.left_panel.isVisible())

    def _toggle_results_table(self):
        self.results_table.setVisible(not self.results_table.isVisible())

    def _get_current_chart(self):
        idx = self.tabs.currentIndex()
        if idx == 0:
            return self.bar_chart
        elif idx == 1:
            return self.pdos_chart
        else:
            return self.multi_pdos_chart

    def _open_data_settings(self):
        chart = self._get_current_chart()
        if hasattr(chart, 'labels_dlg'):
            chart.labels_dlg.show()
            chart.labels_dlg.raise_()
        elif hasattr(chart, 'data_dlg'):
            chart.data_dlg.show()
            chart.data_dlg.raise_()

    def _open_style_settings(self):
        chart = self._get_current_chart()
        if hasattr(chart, 'legend_dlg'):
            chart.legend_dlg.show()
            chart.legend_dlg.raise_()
        elif hasattr(chart, 'style_dlg'):
            chart.style_dlg.show()
            chart.style_dlg.raise_()

    def _open_pattern_settings(self):
        chart = self._get_current_chart()
        if hasattr(chart, 'pattern_dlg'):
            chart.pattern_dlg.show()
            chart.pattern_dlg.raise_()

    def _open_axes_settings(self):
        chart = self._get_current_chart()
        if hasattr(chart, 'axes_dlg'):
            chart.axes_dlg.show()
            chart.axes_dlg.raise_()

    def _reset_chart_view(self):
        chart = self._get_current_chart()
        # 1. Clear explicitly set coordinate ranges
        if hasattr(chart, 'axes_dlg') and hasattr(chart.axes_dlg, 'entry_x_min'):
            # Block signals to prevent redundant redrawing
            chart.axes_dlg.entry_x_min.blockSignals(True)
            chart.axes_dlg.entry_x_max.blockSignals(True)
            chart.axes_dlg.entry_y_min.blockSignals(True)
            chart.axes_dlg.entry_y_max.blockSignals(True)
            
            chart.axes_dlg.entry_x_min.setText("")
            chart.axes_dlg.entry_x_max.setText("")
            chart.axes_dlg.entry_y_min.setText("")
            chart.axes_dlg.entry_y_max.setText("")
            
            chart.axes_dlg.entry_x_min.blockSignals(False)
            chart.axes_dlg.entry_x_max.blockSignals(False)
            chart.axes_dlg.entry_y_min.blockSignals(False)
            chart.axes_dlg.entry_y_max.blockSignals(False)
            
            # Emit update to actually redraw without explicit limits
            chart.axes_dlg.real_time_update.emit()

        # 2. Reset Matplotlib's native navigation stack (for native mouse zoom)
        if hasattr(chart, 'toolbar'):
            chart.toolbar.home()

    def _toggle_global_grid(self):
        chart = self._get_current_chart()
        if hasattr(chart, 'axes_dlg') and hasattr(chart.axes_dlg, 'chk_grid'):
            current = chart.axes_dlg.chk_grid.isChecked()
            chart.axes_dlg.chk_grid.setChecked(not current)

    # ---------- workspace ----------
    def _save_workspace(self):
        """Save current file list, results, and preferences to JSON."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Workspace", "workspace.json",
            "Workspace (*.json)")
        if not path:
            return
        try:
            self._collect_params()
            self.state.save_workspace(path)
            self.statusBar().showMessage(f"Workspace saved \u2192 {path}")
            QMessageBox.information(self, "Workspace Saved",
                                    f"Workspace saved to:\n{path}\n\n"
                                    f"Note: Parsed cache is not saved.\n"
                                    f"Re-run calculation after loading.")
        except OSError as e:
            QMessageBox.critical(self, "Save Failed", f"Cannot save workspace:\n{e}")

    def _load_workspace(self):
        """Load file list, results, and preferences from JSON."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Workspace", "", "Workspace (*.json)")
        if not path:
            return
        try:
            self.state.load_workspace(path)
            self.file_panel._restore_entries(self.state.file_entries)
            self.results_table.populate(self.state.results_data)
            self.bar_chart.update_chart(self.state.results_data)
            self.pdos_chart.update_systems(list(self.state.parsed_cache.keys()))
            self._restore_params()
            self.statusBar().showMessage(
                f"Workspace loaded \u2192 {path} "
                f"({len(self.state.file_entries)} files, "
                f"{len(self.state.results_data)} results)")
            QMessageBox.information(self, "Workspace Loaded",
                                    f"Loaded {len(self.state.file_entries)} file(s) "
                                    f"and {len(self.state.results_data)} result(s).\n\n"
                                    f"Note: Re-run calculation to rebuild parsed cache.")
        except Exception as e:
            QMessageBox.critical(self, "Load Failed", f"Cannot load workspace:\n{e}")

    def _collect_params(self):
        """Collect calculation parameters into state for serialization."""
        self.state.params = {
            "atoms": self.param_panel.get_atoms_text(),
            "spin": self.param_panel.get_spin_mode(),
            "range_all": self.param_panel.chk_all.isChecked(),
            "range_fermi": self.param_panel.chk_fermi.isChecked(),
            "range_custom": self.param_panel.chk_custom.isChecked(),
            "emin": self.param_panel.entry_emin.text(),
            "emax": self.param_panel.entry_emax.text(),
        }

    def _restore_params(self):
        """Restore calculation parameters from state."""
        p = self.state.params
        if not p:
            return
        self.param_panel.entry_atoms.setText(p.get("atoms", ""))
        spin = p.get("spin", "total")
        if spin == "up":
            self.param_panel.radio_up.setChecked(True)
        elif spin == "down":
            self.param_panel.radio_dn.setChecked(True)
        else:
            self.param_panel.radio_tot.setChecked(True)
        self.param_panel.chk_all.setChecked(p.get("range_all", True))
        self.param_panel.chk_fermi.setChecked(p.get("range_fermi", True))
        self.param_panel.chk_custom.setChecked(p.get("range_custom", False))
        self.param_panel.entry_emin.setText(p.get("emin", "-8"))
        self.param_panel.entry_emax.setText(p.get("emax", "0"))

    # ---------- signal wiring ----------
    def _connect_signals(self):
        self.file_panel.files_changed.connect(self._on_files_changed)
        self.file_panel.label_renamed.connect(self._sync_renamed_label)
        self.file_panel.clear_requested.connect(self._on_clear_all)
        self.results_table.row_selected.connect(self._on_result_row_selected)
        self.pdos_chart.system_requested.connect(self._on_pdos_system_requested)
        self.param_panel.combo_method.currentIndexChanged.connect(
            self._on_integration_method_changed)

    def _on_integration_method_changed(self, _index):
        """Make old table/plot values visibly stale after a method change."""
        method = self.param_panel.get_integration_method()
        method_name = "Simpson (SciPy)" if method == "simpson" else "Trapezoid (NumPy)"
        self.statusBar().showMessage(tr(
            f"Integration changed to {method_name}. Run Calculation to refresh all results."
        ))

    def _on_pdos_system_requested(self, label):
        table = self.results_table.data_table
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.text() == label:
                self.results_table.selectRow(row)
                break

    def _on_files_changed(self):
        self.statusBar().showMessage(tr(
            f"Loaded {len(self.state.file_entries)} file(s)."))

    def _on_clear_all(self):
        self.state.results_data.clear()
        self.state.parsed_cache.clear()
        self.results_table.setRowCount(0)
        self.bar_chart.clear_chart()
        self.pdos_chart.clear_chart()
        self.pdos_chart.update_systems([])
        self.multi_pdos_chart.clear_chart()
        if hasattr(self, '_hyb_win') and self._hyb_win.isVisible():
            self._hyb_win.close()
        self.statusBar().showMessage(tr("Cleared."))

    def _sync_renamed_label(self, old_label, new_label):
        """Propagate rename through all data and UI."""
        if old_label in self.state.parsed_cache:
            self.state.parsed_cache[new_label] = self.state.parsed_cache.pop(old_label)
        for rd in self.state.results_data:
            if rd.label == old_label:
                rd.label = new_label
        self.results_table.update_label(old_label, new_label)
        if self.state.results_data:
            self.bar_chart.update_chart(self.state.results_data)
        if (self.pdos_chart._current_label == old_label and
                new_label in self.state.parsed_cache):
            self.pdos_chart.draw_pdos(new_label, self.state.parsed_cache[new_label])
        if self.state.results_data:
            self.multi_pdos_chart.update_data(self.state.parsed_cache, self.state.results_data)
        self.pdos_chart.update_systems(list(self.state.parsed_cache.keys()))

    def _on_result_row_selected(self, label, range_name):
        if label in self.state.parsed_cache:
            self.pdos_chart.set_current_range(range_name)
            self.pdos_chart.draw_pdos(label, self.state.parsed_cache[label])
            self.tabs.setCurrentIndex(1)

    # ---------- calculation ----------
    @staticmethod
    def _calculation_status_text(current, total, method):
        """Human-readable provenance for a live calculation task."""
        method_name = "Simpson (SciPy)" if method == "simpson" else "Trapezoid (NumPy)"
        return tr(f"Calculating {current}/{total} file(s) using {method_name}...")

    def run_calculation(self):
        if not self.state.file_entries:
            QMessageBox.warning(self, "Warning", "Add files first.")
            return

        chosen_type = self.file_panel.get_file_type()
        atoms = self.param_panel.get_atoms_text()
        spin = self.param_panel.get_spin_mode()
        do_all, do_fermi, do_custom, custom_range = self.param_panel.get_range_config()
        integration_method = self.param_panel.get_integration_method()
        self._active_integration_method = integration_method

        # Sync integration method to chart widgets so center annotations match table
        self.pdos_chart.set_integration_method(integration_method)
        self.multi_pdos_chart.set_integration_method(integration_method)
        if hasattr(self, '_hyb_win') and self._hyb_win:
            self._hyb_win.set_integration_method(integration_method)

        if not do_all and not do_fermi and not do_custom:
            QMessageBox.warning(self, "Warning", "Select at least one integration range.")
            return
        if do_custom and custom_range is None:
            QMessageBox.warning(self, "Warning", "Invalid Emin / Emax for custom range.")
            return

        # Disable the Run button during computation
        self.btn_run.setEnabled(False)
        self.state.results_data.clear()
        self.state.parsed_cache.clear()

        self._error_count = 0
        self._ef_warned = False  # one-shot VASPKIT ef=0 warning across the batch
        self._worker = CalculationWorker(
            self.state.file_entries, chosen_type, atoms, spin,
            do_all, do_fermi, do_custom, custom_range,
            integration_method=integration_method, parent=self)

        total = len(self.state.file_entries)
        self._progress = QProgressDialog(
            tr("Calculating d-band centers..."), tr("Cancel"), 0, total, self)
        self._progress.setWindowTitle("Processing")
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setValue(0)

        self._worker.progress.connect(self._progress.setValue)
        self._worker.progress.connect(
            lambda current, total: self.statusBar().showMessage(
                self._calculation_status_text(current, total, integration_method)))
        self._worker.file_done.connect(
            lambda lbl: self._progress.setLabelText(tr(f"Completed: {lbl}")))
        self._worker.file_error.connect(self._on_worker_file_error)
        self._worker.ef_warning.connect(self._on_ef_warning)
        self._worker.calculation_done.connect(self._on_calculation_done)
        self._worker.finished.connect(self._worker.deleteLater)

        self._progress.canceled.connect(self._worker.cancel)
        self._worker.start()

    # Exception class name → display severity mapping
    _WARN_EXCEPTIONS = (
        MissingProjectedDOSError, AtomNotFoundError, FileTypeError,
        OrbitalMissingError, VASPKitAtomError, AmbiguousLayoutError,
        FileIntegrityError, OrbitalUnavailableError, StructureMismatchError,
        AtomSelectionError, UnsupportedLayoutError,
    )

    def _on_worker_file_error(self, label, err_type, message):
        """Handle file error from worker — show dialog on main thread."""
        self._error_count += 1
        title = err_type if err_type != "UnexpectedError" else "Error"
        # Determine severity by matching class name to exception hierarchy
        exc_cls = next(
            (cls for cls in self._WARN_EXCEPTIONS if cls.__name__ == err_type),
            None,
        )
        if exc_cls is not None:
            QMessageBox.warning(self, err_type, f"'{label}': {message}")
        elif err_type == "UnexpectedError":
            QMessageBox.critical(self, "Unexpected Error", f"'{label}':\n{message}")
        else:
            QMessageBox.critical(self, "Error", f"'{label}':\n{message}")

    def _on_ef_warning(self, label):
        """VASPKIT files do not embed the Fermi level — warn once per batch."""
        if self._ef_warned:
            return
        self._ef_warned = True
        QMessageBox.information(
            self, "Fermi Level Notice",
            f"'{label}' is a VASPKIT PDOS file which does not contain the Fermi "
            f"energy.\n\nThe energy axis is used as-is (E_F = 0 assumed), so the "
            f"d-band center is reported relative to the VASPKIT zero reference, "
            f"NOT relative to the true Fermi level.\n\nTo obtain Fermi-aligned "
            f"results, use vasprun.xml or DOSCAR from the same calculation, or "
            f"manually shift the energy axis by the known E_F before analysis."
        )

    def _on_calculation_done(self, results_data, parsed_cache):
        """Receive results from worker, update UI."""
        self._progress.close()
        self.btn_run.setEnabled(True)

        self.state.results_data = results_data
        # Merge worker's cache into state (respecting memory-aware LRU)
        for k, v in parsed_cache.items():
            self.state.parsed_cache[k] = v

        self.results_table.populate(self.state.results_data)
        self.bar_chart.update_chart(self.state.results_data)
        self.multi_pdos_chart.update_data(self.state.parsed_cache, self.state.results_data)
        self.pdos_chart.update_systems(list(self.state.parsed_cache.keys()))
        if self.state.results_data:
            self.results_table.selectRow(0)

        n_ok = len(self.state.file_entries) - self._error_count
        self.statusBar().showMessage(
            f"Done — {n_ok}/{len(self.state.file_entries)} files, "
            f"{len(self.state.results_data)} result rows "
            f"({ 'Simpson (SciPy)' if self._active_integration_method == 'simpson' else 'Trapezoid (NumPy)' }).")

    # ---------- export ----------
    def export_csv(self):
        if not self.state.results_data:
            QMessageBox.warning(self, "Warning", "No results.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "dband_results.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        try:
            DataExporter.export_results_csv(self.state.results_data, path)
            self.statusBar().showMessage(tr(f"CSV exported \u2192 {path}"))
            QMessageBox.information(self, "Success", f"Exported to:\n{path}")
        except OSError as e:
            QMessageBox.critical(self, "Export Failed", f"Cannot write CSV:\n{e}")

    def save_chart(self):
        chart_specs = {
            0: ("dband_center_summary", self.bar_chart.fig,
                bool(self.state.results_data)),
            1: (f"{self.pdos_chart._current_label or 'system'}_PDOS",
                self.pdos_chart.get_figure(),
                bool(self.pdos_chart._current_label)),
            2: ("multi_system_PDOS", self.multi_pdos_chart.get_figure(),
                bool(self.multi_pdos_chart._parsed_cache)),
        }
        stem, fig, has_data = chart_specs[self.tabs.currentIndex()]
        if not has_data:
            QMessageBox.warning(
                self, "Nothing to Export",
                "Generate this chart before exporting it.")
            return

        try:
            initial_dir = ensure_export_directory(self.state.file_entries)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export Folder Error",
                f"Cannot open the preferred export folder:\n{exc}")
            return
        initial_path = initial_dir / f"{stem}.png"
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Current Image", str(initial_path),
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if not path:
            return

        selected_format = next(
            (name.lower() for name in ("PNG", "PDF", "SVG")
             if selected_filter.startswith(name)), "png")
        output_path = selected_export_path(path, selected_format)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            DataExporter.save_figure(fig, str(output_path))
        except OSError as exc:
            QMessageBox.critical(
                self, "Export Failed", f"Cannot save image:\n{exc}")
            return

        remember_export_directory(output_path.parent)
        self.statusBar().showMessage(tr(f"Chart saved \u2192 {output_path}"))
        QMessageBox.information(
            self, "Success", f"Chart saved to:\n{output_path}")

    def batch_export_images(self):
        """Open the batch dialog and export the current visual style as a set."""
        labels = list(self.state.parsed_cache.keys())
        has_summary = bool(self.state.results_data and self.bar_chart.fig.axes)
        has_multi = bool(
            self.multi_pdos_chart._parsed_cache and
            self.multi_pdos_chart.fig.axes and
            self.multi_pdos_chart.data_dlg.combo_systems.get_checked_items())
        if not labels and not has_summary and not has_multi:
            QMessageBox.warning(
                self, "Nothing to Export",
                "Run a calculation and generate charts before batch exporting.")
            return

        dialog = ImageExportDialog(
            labels=labels,
            initial_directory=get_export_directory(self.state.file_entries),
            has_summary=has_summary,
            has_multi=has_multi,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.options()

        try:
            options.output_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export Failed",
                f"Cannot create the output folder:\n{exc}")
            return

        total = (
            len(options.system_labels) if options.include_individual_pdos else 0
        ) + int(options.include_bar_chart) + int(options.include_multi_pdos)
        progress = QProgressDialog(
            tr("Preparing image export..."), tr("Cancel"), 0, total, self)
        progress.setWindowTitle("Batch Export Images")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        def update_progress(done, description):
            progress.setLabelText(tr(description))
            progress.setValue(done)
            QApplication.processEvents()

        result = self._export_batch_images(
            options,
            progress_callback=update_progress,
            is_cancelled=progress.wasCanceled,
        )
        progress.setValue(total)
        progress.close()
        remember_export_directory(options.output_directory)
        self._show_batch_export_result(result, options.output_directory)

    def _export_batch_images(self, options: ImageExportOptions,
                             progress_callback=None, is_cancelled=None):
        """Export images without changing the user's final visible PDOS view."""
        result = BatchImageExportResult()
        progress_callback = progress_callback or (lambda _done, _text: None)
        is_cancelled = is_cancelled or (lambda: False)
        output_dir = Path(options.output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = f".{options.image_format.lower()}"
        done = 0

        previous_label = self.pdos_chart._current_label
        previous_cache = self.pdos_chart._current_cache

        try:
            if options.include_individual_pdos:
                for label in options.system_labels:
                    if is_cancelled():
                        result.cancelled = True
                        break
                    cache_entry = self.state.parsed_cache.get(label)
                    if cache_entry is None:
                        result.failures.append(
                            (label, "Analyzed PDOS data is unavailable."))
                    else:
                        try:
                            self.pdos_chart.draw_pdos(label, cache_entry)
                            output_path = available_export_path(
                                output_dir, f"{label}_PDOS", suffix)
                            DataExporter.save_figure(
                                self.pdos_chart.get_figure(), str(output_path),
                                dpi=options.dpi)
                            result.exported.append(str(output_path))
                        except Exception as exc:
                            result.failures.append((label, str(exc)))
                    done += 1
                    progress_callback(done, f"Exported individual PDOS: {label}")
        finally:
            # Batch rendering temporarily visits each system.  Always return
            # to the exact system the user was editing before export.
            try:
                if previous_label and previous_cache is not None:
                    self.pdos_chart.draw_pdos(previous_label, previous_cache)
                else:
                    self.pdos_chart._current_label = None
                    self.pdos_chart._current_cache = None
                    self.pdos_chart.fig.clear()
                    self.pdos_chart.canvas.draw()
                    self.pdos_chart.update_systems(
                        list(self.state.parsed_cache.keys()))
            except Exception as exc:
                result.failures.append(("Restore PDOS view", str(exc)))

        summary_tasks = (
            ("D-band center summary", options.include_bar_chart,
             self.bar_chart.fig, "dband_center_summary"),
            ("Multi-system PDOS", options.include_multi_pdos,
             self.multi_pdos_chart.get_figure(), "multi_system_PDOS"),
        )
        for title, included, figure, stem in summary_tasks:
            if not included or result.cancelled:
                continue
            if is_cancelled():
                result.cancelled = True
                break
            try:
                output_path = available_export_path(output_dir, stem, suffix)
                DataExporter.save_figure(
                    figure, str(output_path), dpi=options.dpi)
                result.exported.append(str(output_path))
            except Exception as exc:
                result.failures.append((title, str(exc)))
            done += 1
            progress_callback(done, f"Exported: {title}")

        return result

    def _show_batch_export_result(self, result, output_directory):
        count = len(result.exported)
        failure_count = len(result.failures)
        status = "cancelled" if result.cancelled else "completed"
        self.statusBar().showMessage(tr(
            f"Batch export {status} — {count} saved, {failure_count} failed."))

        box = QMessageBox(self)
        box.setWindowTitle("Batch Export Images")
        box.setIcon(
            QMessageBox.Warning if failure_count else QMessageBox.Information)
        box.setText(
            f"Batch export {status}.\n\n"
            f"Saved: {count}\nFailed: {failure_count}\n"
            f"Folder: {output_directory}")
        if result.failures:
            box.setDetailedText("\n".join(
                f"{name}: {message}" for name, message in result.failures))
        open_button = None
        if count:
            open_button = box.addButton(
                "Open Export Folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if open_button is not None and box.clickedButton() is open_button:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(output_directory)))

    # ---------- Help controls ----------
    def _open_documentation(self):
        dlg = DocumentationDialog(self)
        dlg.exec()

    def _open_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def _open_hybridization(self):
        from ui.hybridization_win import HybridizationWindow
        self._hyb_win = HybridizationWindow(self.state, parent=self)
        self._hyb_win.set_dark_mode(getattr(self, 'is_dark_mode', False))
        # Sync current integration method selection so chart annotations
        # match the main table.
        current_method = self.param_panel.get_integration_method()
        self._hyb_win.set_integration_method(current_method)
        self._hyb_win.show()
