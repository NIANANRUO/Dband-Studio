"""
Orbital Hybridization Analysis Window.
Independent full-screen window for analyzing orbital hybridization between
metal center and ligand fragments.

v4.0: Async parsing via HybridizationWorker + local cache to prevent UI freezing.
Theme/range changes only re-render, never re-parse.
"""
import numpy as np

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QScrollArea, QFileDialog, QMessageBox, QTabWidget, QFrame,
    QDoubleSpinBox, QDialog, QColorDialog, QSizePolicy
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal
from matplotlib.figure import Figure
from matplotlib.colors import to_hex, to_rgb
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from core.exceptions import (
    DbandError, FileTypeError, OrbitalMissingError, AtomSelectionError,
    VASPKitAtomError, AtomNotFoundError, MissingProjectedDOSError,
)
from core.parsers import s_orb_names, p_orb_names, d_orb_names, f_orb_names
from core.calculator import calc_metrics
from core.orbital_selection import non_overlapping_orbitals
from utils.styling import annotate_center
from core.services.hybridization_worker import HybridizationWorker
from core.services.exporter import DataExporter, selected_export_path
from core.loader import DataLoader
from core.pdos_metadata import input_context_from_entry
from utils.styling import (
    CENTER_COLOR, CENTER_LW, CENTER_FONTSIZE,
    HYB_FRAG1_COLOR, HYB_FRAG2_COLOR,
    HYB_METAL_CENTER_COLOR, HYB_LIGAND_CENTER_COLOR,
    BTN_HYB_COLOR, DECOMP_COLORS, THEMES_CONFIG,
)
from utils.helpers import format_orbital_display
from utils.export_paths import ensure_export_directory, remember_export_directory
from ui.widgets.range_selector import RangeSelectorWidget
from ui.widgets.collapsible import CollapsibleWidget
from ui.i18n import (
    combo_value, find_combo_value, get_language_manager, localized_stylesheet,
    set_combo_value, set_translated_text, tr,
)


class FragmentPanel(QFrame):
    """Panel for defining one fragment (Metal or Ligand)."""
    orbitals_changed = Signal()
    input_changed = Signal()

    def __init__(self, title, state, parent=None):
        super().__init__(parent)
        self.setObjectName("LeftCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.state = state
        self._orbital_checks = {}
        self.title_text = title
        self._build_ui()

    def _make_connections(self, chk_all_btn, check_list):
        def on_all_toggled(_checked):
            self.orbitals_changed.emit()
            
        def on_indiv_toggled():
            self.orbitals_changed.emit()
            
        chk_all_btn.toggled.connect(on_all_toggled)
        for c in check_list:
            c.toggled.connect(on_indiv_toggled)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        lbl = QLabel(f"<b>{self.title_text}</b>")
        layout.addWidget(lbl)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Alias (optional):"))
        self.entry_alias = QLineEdit()
        self.entry_alias.setPlaceholderText("e.g. Metal")
        self.entry_alias.textChanged.connect(lambda _text: self.input_changed.emit())
        row1.addWidget(self.entry_alias)
        layout.addLayout(row1)

        row_src = QHBoxLayout()
        row_src.addWidget(QLabel("Data Source:"))
        self.combo_file = QComboBox()
        self.combo_file.setProperty("_i18n_skip_items", True)
        self.combo_file.currentIndexChanged.connect(self._on_source_changed)
        row_src.addWidget(self.combo_file)
        layout.addLayout(row_src)

        row_atoms = QHBoxLayout()
        row_atoms.addWidget(QLabel("Atoms:"))
        self.entry_atoms = QLineEdit()
        self.entry_atoms.textChanged.connect(lambda _text: self.input_changed.emit())
        row_atoms.addWidget(self.entry_atoms)
        layout.addLayout(row_atoms)

        self.orbs_widget = CollapsibleWidget("VASP Projected Orbitals")
        orbs_main_layout = QVBoxLayout()
        orbs_main_layout.setContentsMargins(0, 0, 0, 0)
        orbs_main_layout.setSpacing(6)
        
        for title, orbs in [("s", s_orb_names), ("p", p_orb_names), ("d", d_orb_names), ("f", f_orb_names)]:
            grp = QGroupBox(title)
            vbox = QVBoxLayout(grp)
            vbox.setContentsMargins(8, 12, 8, 8)
            vbox.setSpacing(4)
            
            chk_all = QCheckBox(f"{title}-total")
            self._orbital_checks[title] = chk_all
            chk_all.setToolTip(
                f"Merged VASP {title} projection. This is not a principal-quantum-number shell.")
            vbox.addWidget(chk_all)
            
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(4)
            
            checks = []
            row = col = 0
            for orb in orbs:
                if orb == title:
                    continue
                chk = QCheckBox(format_orbital_display(orb))
                self._orbital_checks[orb] = chk
                checks.append(chk)
                grid.addWidget(chk, row, col)
                col += 1
                if col > 3:
                    col = 0
                    row += 1
            vbox.addLayout(grid)
            
            self._make_connections(chk_all, checks)
            orbs_main_layout.addWidget(grp)
            
        self.orbs_widget.add_layout(orbs_main_layout)
        layout.addWidget(self.orbs_widget)

    def refresh_sources(self):
        current = combo_value(self.combo_file)
        self.combo_file.clear()
        items = []
        for i, entry in enumerate(self.state.file_entries, 1):
            items.append(f"{i}. {entry['label']}")
        self.combo_file.addItems(items)
        idx = find_combo_value(self.combo_file, current)
        if idx >= 0:
            self.combo_file.setCurrentIndex(idx)
        self._apply_source_capabilities()

    def _on_source_changed(self, _index):
        self._apply_source_capabilities()
        self.input_changed.emit()

    def _apply_source_capabilities(self):
        idx = self.combo_file.currentIndex()
        if idx < 0 or idx >= len(self.state.file_entries):
            return
        entry = self.state.file_entries[idx]
        capabilities = entry.get("capabilities") or {}
        available = set(capabilities.get("available_orbitals", ()))
        if not available:
            for check in self._orbital_checks.values():
                check.setEnabled(True)
                check.setToolTip("")
            return
        groups = {
            "s": tuple(s_orb_names), "p": tuple(p_orb_names),
            "d": tuple(d_orb_names), "f": tuple(f_orb_names),
        }
        for total, components in groups.items():
            total_check = self._orbital_checks[total]
            total_available = total in available or set(components) <= available
            total_check.setEnabled(total_available)
            if not total_available:
                total_check.setChecked(False)
                total_check.setToolTip(
                    f"{total}-total is unavailable in this source's projected-DOS layout.")
            for component in components:
                if component == total or component not in self._orbital_checks:
                    continue
                check = self._orbital_checks[component]
                enabled = component in available
                check.setEnabled(enabled)
                if not enabled:
                    check.setChecked(False)
                    check.setToolTip(
                        f"{component} is unavailable at "
                        f"{capabilities.get('orbital_resolution', 'unknown')} resolution.")
                else:
                    check.setToolTip("")

    def get_selected_source(self):
        idx = self.combo_file.currentIndex()
        if idx < 0 or idx >= len(self.state.file_entries):
            return None, None
        entry = self.state.file_entries[idx]
        return entry['label'], entry['path']

    def get_input_context(self):
        idx = self.combo_file.currentIndex()
        if idx < 0 or idx >= len(self.state.file_entries):
            return None
        entry = self.state.file_entries[idx]
        capabilities = entry.get("capabilities") or {}
        source_format = capabilities.get("source_format")
        if not source_format:
            source_format = DataLoader.detect(entry["path"])
        return input_context_from_entry(entry, source_format)

    def get_atoms_text(self):
        return self.entry_atoms.text()

    def get_selected_orbitals(self):
        return [oname for oname, chk in self._orbital_checks.items() if chk.isChecked()]

    def get_fragment_name(self):
        text = self.entry_alias.text().strip()
        return text if text else self.title_text

class HybridizationWindow(QMainWindow):
    _FOLLOW_OVERLAP_FRAG1 = "Follow Overlap (Frag 1)"
    _FOLLOW_OVERLAP_FRAG2 = "Follow Overlap (Frag 2)"

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Orbital Hybridization Analysis (Async)")
        self.resize(1100, 800)
        self.state = state
        self._worker = None
        self._batch_display = None
        self._batch_dialog = None
        self._parsed_cache = {}
        self._cached_data = None
        self._has_plot_data = False
        self._request_token = 0
        self._is_dark_mode = False
        self._integration_method = "trapezoid"
        self._build_ui()
        set_combo_value(self.combo_theme_top, self.state.hybridization_style.get(
            "overlap", "Theme 1 (Red-Gray)"))
        self._refresh_sources()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # ---- LEFT: Controls ----
        left_container = QWidget()
        left_container.setFixedWidth(380)
        left_vbox = QVBoxLayout(left_container)
        left_vbox.setContentsMargins(0, 0, 0, 0)

        self.left_tabs = QTabWidget()

        # Tab 1: Fragment 1
        scroll1 = QScrollArea()
        scroll1.setWidgetResizable(True)
        w1 = QWidget()
        w1.setObjectName("scrollContent")
        l1 = QVBoxLayout(w1)
        l1.setAlignment(Qt.AlignTop)
        self.frag1 = FragmentPanel("Fragment 1", self.state)
        l1.addWidget(self.frag1)
        scroll1.setWidget(w1)
        self.left_tabs.addTab(scroll1, "Fragment 1")

        # Tab 2: Fragment 2
        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        w2 = QWidget()
        w2.setObjectName("scrollContent")
        l2 = QVBoxLayout(w2)
        l2.setAlignment(Qt.AlignTop)
        self.frag2 = FragmentPanel("Fragment 2", self.state)
        l2.addWidget(self.frag2)
        scroll2.setWidget(w2)
        self.left_tabs.addTab(scroll2, "Fragment 2")

        # Tab 3: Global Settings
        scroll3 = QScrollArea()
        scroll3.setWidgetResizable(True)
        w3 = QWidget()
        w3.setObjectName("scrollContent")
        l3 = QVBoxLayout(w3)
        l3.setAlignment(Qt.AlignTop)

        # Spin mode
        spin_grp = QGroupBox("Spin Mode")
        spin_layout = QHBoxLayout(spin_grp)
        self.combo_spin = QComboBox()
        self.combo_spin.addItems(["Total", "Spin-Up", "Spin-Down"])
        spin_layout.addWidget(self.combo_spin)
        l3.addWidget(spin_grp)

        # Geometry Analysis Settings
        geom_grp = QGroupBox("Geometry Analysis")
        geom_layout = QGridLayout(geom_grp)
        geom_layout.addWidget(QLabel("Bond Cutoff (Å):"), 0, 0)
        self.spin_cutoff = QDoubleSpinBox()
        self.spin_cutoff.setRange(0.1, 10.0)
        self.spin_cutoff.setSingleStep(0.1)
        self.spin_cutoff.setValue(3.5)
        geom_layout.addWidget(self.spin_cutoff, 0, 1)

        geom_layout.addWidget(QLabel("Mode:"), 1, 0)
        self.combo_geom_mode = QComboBox()
        self.combo_geom_mode.addItems(["All pairs within cutoff", "Shortest bond only"])
        geom_layout.addWidget(self.combo_geom_mode, 1, 1)
        
        geom_layout.addWidget(QLabel("Bond Atoms 1:"), 2, 0)
        self.entry_bond_atoms1 = QLineEdit()
        self.entry_bond_atoms1.setPlaceholderText("e.g. 1-10 (Leave empty to use Frag 1)")
        geom_layout.addWidget(self.entry_bond_atoms1, 2, 1)

        geom_layout.addWidget(QLabel("Bond Atoms 2:"), 3, 0)
        self.entry_bond_atoms2 = QLineEdit()
        self.entry_bond_atoms2.setPlaceholderText("e.g. 11-20 (Leave empty to use Frag 2)")
        geom_layout.addWidget(self.entry_bond_atoms2, 3, 1)

        l3.addWidget(geom_grp)

        # Integration Settings
        integ_grp = QGroupBox("Integration Settings")
        integ_layout = QGridLayout(integ_grp)
        
        integ_layout.addWidget(QLabel("Method:"), 0, 0)
        self.combo_integ_method = QComboBox()
        self.combo_integ_method.addItems(["trapezoid", "simpson"])
        # Set to current global method
        idx = find_combo_value(self.combo_integ_method, self._integration_method)
        if idx >= 0:
            self.combo_integ_method.setCurrentIndex(idx)
        self.combo_integ_method.currentIndexChanged.connect(self._on_integ_method_changed)
        integ_layout.addWidget(self.combo_integ_method, 0, 1)

        integ_layout.addWidget(QLabel("Range:"), 1, 0)
        self.combo_integ_range = QComboBox()
        self.combo_integ_range.addItems(["All", "< Ef", "Custom"])
        self.combo_integ_range.currentIndexChanged.connect(self._on_integ_range_changed)
        integ_layout.addWidget(self.combo_integ_range, 1, 1)

        self.integ_custom_range = RangeSelectorWidget("Custom Range:", show_apply=False)
        self.integ_custom_range.set_range(-10.0, 10.0) # default values
        self.integ_custom_range.range_changed.connect(self._on_setting_changed)
        self.integ_custom_range.setVisible(False)
        integ_layout.addWidget(self.integ_custom_range, 2, 0, 1, 2)

        self.chk_centers_all = QCheckBox("Show d-band Centers on All Panels")
        self.chk_centers_all.setTristate(True)
        self.chk_centers_all.setCheckState(Qt.Checked)
        integ_layout.addWidget(self.chk_centers_all, 3, 0, 1, 2)
        
        l3.addWidget(integ_grp)

        # Global Line/Fill Style
        style_grp = QGroupBox("Global Style")
        style_layout = QGridLayout(style_grp)
        style_layout.addWidget(QLabel("Line Width:"), 0, 0)
        self.spin_lw = QDoubleSpinBox()
        self.spin_lw.setRange(0.5, 5.0)
        self.spin_lw.setSingleStep(0.5)
        self.spin_lw.setValue(1.0)
        self.spin_lw.valueChanged.connect(self._on_setting_changed)
        style_layout.addWidget(self.spin_lw, 0, 1)

        self.chk_fill = QCheckBox("Fill Area")
        self.chk_fill.setChecked(True)
        self.chk_fill.stateChanged.connect(self._on_setting_changed)
        style_layout.addWidget(self.chk_fill, 1, 0)

        self.spin_alpha = QDoubleSpinBox()
        self.spin_alpha.setRange(0.0, 1.0)
        self.spin_alpha.setSingleStep(0.1)
        self.spin_alpha.setValue(0.5)
        self.spin_alpha.setToolTip("Fill Transparency (Alpha)")
        self.spin_alpha.valueChanged.connect(self._on_setting_changed)
        style_layout.addWidget(self.spin_alpha, 1, 1)

        l3.addWidget(style_grp)

        # Plot settings
        settings_grp = QGroupBox("Plot Settings")
        settings_layout = QVBoxLayout(settings_grp)

        self.settings_tabs = QTabWidget()

        # --- Overlap Tab ---
        tab_top = QWidget()
        layout_top = QVBoxLayout(tab_top)
        self.chk_center_top = QCheckBox("Show Center Lines")
        self.chk_center_top.setChecked(True)
        self.chk_center_top.stateChanged.connect(self._on_setting_changed)
        layout_top.addWidget(self.chk_center_top)
        self.x_range_top = RangeSelectorWidget("X range:", show_apply=False)
        self.x_range_top.range_changed.connect(self._on_setting_changed)
        self.y_range_top = RangeSelectorWidget("Y range:", show_apply=False)
        self.y_range_top.range_changed.connect(self._on_setting_changed)
        layout_top.addWidget(self.x_range_top)
        layout_top.addWidget(self.y_range_top)
        self.combo_theme_top = QComboBox()
        self.combo_theme_top.addItems(list(THEMES_CONFIG.get("2_color", {}).keys()))
        self.combo_theme_top.currentIndexChanged.connect(self._on_overlap_theme_changed)
        layout_top.addWidget(QLabel("Theme:"))
        layout_top.addWidget(self.combo_theme_top)
        self.btn_sync_x = QPushButton("Sync X-Range to All")
        self.btn_sync_x.clicked.connect(self._sync_x_ranges)
        layout_top.addWidget(self.btn_sync_x)
        layout_top.addStretch()
        self.settings_tabs.addTab(tab_top, "Overlap")

        # --- Fragment 1 Tab ---
        tab_mid = QWidget()
        layout_mid = QVBoxLayout(tab_mid)
        self.chk_center_mid = QCheckBox("Show Center Lines")
        self.chk_center_mid.setChecked(True)
        self.chk_center_mid.stateChanged.connect(self._on_setting_changed)
        layout_mid.addWidget(self.chk_center_mid)
        self.x_range_mid = RangeSelectorWidget("X range:", show_apply=False)
        self.x_range_mid.range_changed.connect(self._on_setting_changed)
        self.y_range_mid = RangeSelectorWidget("Y range:", show_apply=False)
        self.y_range_mid.range_changed.connect(self._on_setting_changed)
        layout_mid.addWidget(self.x_range_mid)
        layout_mid.addWidget(self.y_range_mid)
        self.combo_theme_mid = QComboBox()
        self.combo_theme_mid.setToolTip(tr("Manual orbital colors take priority over themes. Restore defaults to clear them."))
        self.combo_theme_mid.currentIndexChanged.connect(lambda: self._save_fragment_style(0))
        layout_mid.addWidget(QLabel("Theme:"))
        layout_mid.addWidget(self.combo_theme_mid)
        self._add_color_controls(layout_mid, 0)
        layout_mid.addStretch()
        self.settings_tabs.addTab(tab_mid, "Frag 1")

        # --- Fragment 2 Tab ---
        tab_bot = QWidget()
        layout_bot = QVBoxLayout(tab_bot)
        self.chk_center_bot = QCheckBox("Show Center Lines")
        self.chk_center_bot.setChecked(True)
        self.chk_center_bot.stateChanged.connect(self._on_setting_changed)
        layout_bot.addWidget(self.chk_center_bot)
        self.x_range_bot = RangeSelectorWidget("X range:", show_apply=False)
        self.x_range_bot.range_changed.connect(self._on_setting_changed)
        self.y_range_bot = RangeSelectorWidget("Y range:", show_apply=False)
        self.y_range_bot.range_changed.connect(self._on_setting_changed)
        layout_bot.addWidget(self.x_range_bot)
        layout_bot.addWidget(self.y_range_bot)
        self.combo_theme_bot = QComboBox()
        self.combo_theme_bot.setToolTip(tr("Manual orbital colors take priority over themes. Restore defaults to clear them."))
        self.combo_theme_bot.currentIndexChanged.connect(lambda: self._save_fragment_style(1))
        layout_bot.addWidget(QLabel("Theme:"))
        layout_bot.addWidget(self.combo_theme_bot)
        self._add_color_controls(layout_bot, 1)
        layout_bot.addStretch()
        self.settings_tabs.addTab(tab_bot, "Frag 2")

        self.chk_centers_all.stateChanged.connect(
            self._set_all_center_visibility)
        for center_check in (
            self.chk_center_top, self.chk_center_mid, self.chk_center_bot,
        ):
            center_check.stateChanged.connect(
                self._sync_global_center_visibility)

        settings_layout.addWidget(self.settings_tabs)
        l3.addWidget(settings_grp)
        
        export_row = QHBoxLayout()
        btn_csv = QPushButton("Export DOS CSV")
        btn_csv.clicked.connect(self._export_csv)
        export_row.addWidget(btn_csv)
        btn_png = QPushButton("Save Plot PNG")
        btn_png.clicked.connect(self._save_png)
        export_row.addWidget(btn_png)
        l3.addLayout(export_row)

        l3.addStretch()
        scroll3.setWidget(w3)
        self.left_tabs.addTab(scroll3, "⚙️ Settings")

        left_vbox.addWidget(self.left_tabs)

        # Source/atom/orbital changes invalidate prior DOS arrays.  Reusing an
        # old plot after such a change would be a scientifically false result.
        self.frag1.input_changed.connect(self._on_fragment_input_changed)
        self.frag2.input_changed.connect(self._on_fragment_input_changed)
        self.frag1.orbitals_changed.connect(self._on_fragment_input_changed)
        self.frag2.orbitals_changed.connect(self._on_fragment_input_changed)
        self.frag1.orbitals_changed.connect(self._update_mid_themes)
        self.frag2.orbitals_changed.connect(self._update_bot_themes)
        self._update_mid_themes()
        self._update_bot_themes()

        # Action button at bottom
        self.btn_batch = QPushButton("Batch analysis…")
        self.btn_batch.clicked.connect(self._open_batch)
        left_vbox.addWidget(self.btn_batch)
        self.btn_plot = QPushButton("🚀 Run Comprehensive Analysis")
        self.btn_plot.setFixedHeight(45)
        self.btn_plot.setProperty("isPrimary", "true")
        self.btn_plot.clicked.connect(self._generate_plot)
        left_vbox.addWidget(self.btn_plot)

        root.addWidget(left_container)

        # ---- RIGHT: Plot and Table Area ----
        self.right_tabs = QTabWidget()

        # 1. Plot Tab
        plot_tab = QWidget()
        plot_layout = QVBoxLayout(plot_tab)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self.fig = Figure(constrained_layout=True)
        self._ax_top, self._ax_mid, self._ax_bot = self.fig.subplots(
            3, 1, gridspec_kw={"height_ratios": [1.2, 2, 1.2]})
        self.canvas = FigureCanvas(self.fig)
        plot_layout.addWidget(self.canvas)
        self.right_tabs.addTab(plot_tab, "📈 Hybridization Plot")

        # 2. Table Tab
        table_tab = QWidget()
        table_layout = QVBoxLayout(table_tab)
        
        table_toolbar = QHBoxLayout()
        self.btn_export_dist = QPushButton("📥 Export Bond Lengths to CSV")
        self.btn_export_dist.clicked.connect(self._export_distances_csv)
        self.btn_export_dist.setEnabled(False)
        table_toolbar.addWidget(self.btn_export_dist)
        table_toolbar.addStretch()
        table_layout.addLayout(table_toolbar)

        from PySide6.QtWidgets import QTableWidget, QAbstractItemView, QHeaderView
        self.table_dist = QTableWidget()
        self.table_dist.setColumnCount(3)
        self.table_dist.setHorizontalHeaderLabels(["Fragment 1 Atom", "Fragment 2 Atom", "Distance (Å)"])
        self.table_dist.verticalHeader().setVisible(False)
        self.table_dist.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_dist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_dist.setSortingEnabled(True)
        table_layout.addWidget(self.table_dist)

        self.right_tabs.addTab(table_tab, "📏 Bond Length Statistics")

        root.addWidget(self.right_tabs, 1)

    def _open_batch(self):
        if self._worker and self._worker.isRunning():
            return
        if self._batch_dialog is None:
            from ui.hybridization_batch_dialog import HybridizationBatchDialog
            self._batch_dialog = HybridizationBatchDialog(self)
            self._batch_dialog.result_selected.connect(self._show_batch_result)
        self._batch_dialog.show()
        self._batch_dialog.raise_()

    def _show_batch_result(self, task, data):
        self._batch_display = (','.join(map(str, task.left)), ','.join(map(str, task.right)), task.spin)
        self._cached_data = data
        self._has_plot_data = True
        self._render_plot(*data)
        from core.services.hybridization_worker import GeometryAnalysisResult
        self._update_distance_table(GeometryAnalysisResult(None,
            tr('Batch result: bond lengths are not included. Use single analysis for geometry.')))
        self.statusBar().showMessage(task.title())

    def closeEvent(self, event):
        if self._batch_dialog and ((self._batch_dialog.worker and self._batch_dialog.worker.isRunning())
                                   or self._batch_dialog._export_queue is not None):
            self._batch_dialog._cancel()
            event.ignore()
            return
        if self._worker and getattr(self._worker, "isRunning", lambda: False)():
            event.ignore()
            return
        super().closeEvent(event)

    def _refresh_sources(self):
        self.frag1.refresh_sources()
        self.frag2.refresh_sources()

    # ---------- async parsing ----------

    def _on_integ_method_changed(self):
        self._integration_method = combo_value(self.combo_integ_method)
        self._on_setting_changed()
        
    def _on_integ_range_changed(self):
        is_custom = combo_value(self.combo_integ_range) == "Custom"
        self.integ_custom_range.setVisible(is_custom)
        self._on_setting_changed()

    def _get_integration_limits(self):
        mode = combo_value(self.combo_integ_range)
        if mode == "< Ef":
            return True, None, "< Ef"
        elif mode == "Custom":
            xmin, xmax = self.integ_custom_range.get_range()
            if xmin is not None and xmax is not None:
                return False, (xmin, xmax), f"[{xmin:.2f}, {xmax:.2f}]"
            return False, None, "All" # Fallback if invalid
        return False, None, "All"

    def _on_setting_changed(self):
        """Theme/range/checkbox changed — re-render only, no re-parse."""
        if self._has_plot_data and self._cached_data:
            self._render_plot(*self._cached_data)
        else:
            self.statusBar().showMessage(tr("Waiting for plot generation..."))

    def _on_fragment_input_changed(self):
        """Prevent stale DOS/annotations from surviving an input mutation."""
        self._request_token += 1
        self._cached_data = None
        self._has_plot_data = False
        # Never leave a plot on screen once its file, atom selection, or
        # orbitals changed: that would make old DOS look like fresh data.
        for ax in (self._ax_top, self._ax_mid, self._ax_bot):
            ax.clear()
        self.fig.suptitle(
            tr("Input changed — generate a new hybridization analysis"), fontsize=11)
        self.canvas.draw_idle()

        from PySide6.QtWidgets import QTableWidgetItem
        self.table_dist.clearSpans()
        self.table_dist.setRowCount(1)
        item = QTableWidgetItem("Input changed — regenerate before interpreting bond lengths")
        item.setTextAlignment(Qt.AlignCenter)
        self.table_dist.setItem(0, 0, item)
        self.table_dist.setSpan(0, 0, 1, 3)
        self.btn_export_dist.setEnabled(False)
        self.statusBar().showMessage(tr(
            "Fragment input changed. Generate a new analysis before interpreting the plot."
        ))

    def _get_spin_mode(self):
        text = combo_value(self.combo_spin)
        if text == "Spin-Up":
            return "up"
        elif text == "Spin-Down":
            return "down"
        return "total"

    def _collect_fragment_params(self, frag_panel):
        """Collect parameters for HybridizationWorker."""
        label, fp = frag_panel.get_selected_source()
        atoms = frag_panel.get_atoms_text()
        orbitals = frag_panel.get_selected_orbitals()
        spin = self._get_spin_mode()
        alias = frag_panel.get_fragment_name()
        context = frag_panel.get_input_context() if fp else None
        return (label, fp, atoms, orbitals, spin, alias, context)

    def _generate_plot(self):
        """Start async parsing in background thread."""
        if self._worker and self._worker.isRunning():
            return  # Prevent duplicate submissions

        self._batch_display = None
        p1 = self._collect_fragment_params(self.frag1)
        p2 = self._collect_fragment_params(self.frag2)

        # Validate basic inputs before starting thread
        label1, fp1, atoms1, orbs1, _, alias1, _ = p1
        label2, fp2, atoms2, orbs2, _, alias2, _ = p2
        if not fp1 or not fp2:
            QMessageBox.warning(self, "Invalid Input", "Please select a data source file for both fragments.")
            return
        if not orbs1 or not orbs2:
            QMessageBox.warning(self, "Invalid Input", "Please select at least one orbital for both fragments.")
            return

        cutoff = self.spin_cutoff.value()
        mode_str = combo_value(self.combo_geom_mode)
        mode = "shortest" if "Shortest" in mode_str else "all"
        
        bond_atoms1 = self.entry_bond_atoms1.text().strip()
        bond_atoms2 = self.entry_bond_atoms2.text().strip()
        b_atoms1 = bond_atoms1 if bond_atoms1 else atoms1
        b_atoms2 = bond_atoms2 if bond_atoms2 else atoms2
        
        geom_params = (cutoff, mode, b_atoms1, b_atoms2)

        # Every calculation owns one immutable request token.  If the user
        # changes an input while a worker is parsing, its callback is stale and
        # must never overwrite the newer scientific context.
        self._request_token += 1
        request_token = self._request_token
        self._cached_data = None
        self._has_plot_data = False

        self.btn_plot.setEnabled(False)
        set_translated_text(self.btn_plot, "Analyzing...")
        self.statusBar().showMessage(tr(
            "Parsing data and calculating geometry in background..."))

        self._worker = HybridizationWorker(
            p1, p2, geom_params, self._parsed_cache, self.state.parsed_cache, parent=self)
        self._worker.request_token = request_token
        self._worker.progress.connect(self._show_translated_status)
        # Bound QObject slots are queued onto this window's GUI thread.  Do
        # not replace these with lambdas: a lambda executes in the worker
        # thread and makes matplotlib/Qt rendering hang or crash.
        self._worker.result_ready.connect(self._on_data_ready)
        self._worker.error_occurred.connect(self._on_parse_error_if_current)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_data_ready(self, data1, data2, geometry_result):
        """Background parse complete — render on main thread (~10ms)."""
        if self._worker is None or self._worker.request_token != self._request_token:
            self.statusBar().showMessage(tr(
                "Discarded stale analysis result after fragment input changed."
            ))
            return
        self._cached_data = (data1, data2)
        self._has_plot_data = True
        self._render_plot(data1, data2)
        self._update_distance_table(geometry_result)
        self.statusBar().showMessage(tr(
            "Hybridization plot and geometry analysis generated."))

    def _show_translated_status(self, message):
        """Display worker progress in the active UI language on the GUI thread."""
        self.statusBar().showMessage(tr(message))
        
    def _update_distance_table(self, geometry_result):
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtCore import Qt
        
        self.table_dist.setRowCount(0)
        
        if geometry_result.diagnostic is not None:
            self.table_dist.setRowCount(1)
            item = QTableWidgetItem(geometry_result.diagnostic)
            item.setTextAlignment(Qt.AlignCenter)
            self.table_dist.setItem(0, 0, item)
            self.table_dist.setSpan(0, 0, 1, 3)
            self.btn_export_dist.setEnabled(False)
            return

        distance_results = geometry_result.pairs

        if distance_results is None:
            self.table_dist.setRowCount(1)
            item = QTableWidgetItem("Geometry analysis was not requested for this task")
            item.setTextAlignment(Qt.AlignCenter)
            self.table_dist.setItem(0, 0, item)
            self.table_dist.setSpan(0, 0, 1, 3)
            self.btn_export_dist.setEnabled(False)
            return

        if len(distance_results) == 0:
            self.table_dist.setRowCount(1)
            item = QTableWidgetItem("No bonds found within cutoff distance")
            item.setTextAlignment(Qt.AlignCenter)
            self.table_dist.setItem(0, 0, item)
            self.table_dist.setSpan(0, 0, 1, 3)
            self.btn_export_dist.setEnabled(False)
            return
            
        self.table_dist.clearSpans()
        self.table_dist.setRowCount(len(distance_results))
        for row, (sym1, sym2, dist) in enumerate(distance_results):
            item1 = QTableWidgetItem(sym1)
            item2 = QTableWidgetItem(sym2)
            item3 = QTableWidgetItem(f"{dist:.4f}")
            item3.setData(Qt.UserRole, dist) # For numerical sorting
            
            item1.setTextAlignment(Qt.AlignCenter)
            item2.setTextAlignment(Qt.AlignCenter)
            item3.setTextAlignment(Qt.AlignCenter)
            
            self.table_dist.setItem(row, 0, item1)
            self.table_dist.setItem(row, 1, item2)
            self.table_dist.setItem(row, 2, item3)
            
        self.btn_export_dist.setEnabled(True)
        
    def _export_distances_csv(self):
        import csv
        from PySide6.QtWidgets import QFileDialog
        
        if self.table_dist.rowCount() == 0 or self.table_dist.columnSpan(0, 0) > 1:
            return
            
        fp, _ = QFileDialog.getSaveFileName(self, "Export Bond Lengths", "", "CSV Files (*.csv)")
        if not fp:
            return
            
        try:
            with open(fp, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Fragment 1 Atom", "Fragment 2 Atom", "Distance (Angstroms)"])
                for row in range(self.table_dist.rowCount()):
                    sym1 = self.table_dist.item(row, 0).text()
                    sym2 = self.table_dist.item(row, 1).text()
                    dist = self.table_dist.item(row, 2).text()
                    writer.writerow([sym1, sym2, dist])
            QMessageBox.information(self, "Success", f"Bond lengths exported to {fp}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export CSV: {e}")

    # Exception classes that warrant a warning (not critical) dialog
    _WARN_EXCEPTIONS = (
        FileTypeError, DbandError, OrbitalMissingError, AtomSelectionError,
        VASPKitAtomError, AtomNotFoundError, MissingProjectedDOSError,
    )

    def _on_parse_error(self, err_type, message):
        """Handle parse error from worker."""
        # ValueError is emitted by the worker for invalid user input
        # (missing file / orbital) and must be treated as a warning, not critical.
        if err_type == "ValueError":
            QMessageBox.warning(self, "Invalid Input", message)
            return
        exc_cls = next(
            (cls for cls in self._WARN_EXCEPTIONS if cls.__name__ == err_type),
            None,
        )
        if exc_cls == FileTypeError:
            QMessageBox.warning(self, "Unknown File Type", message)
        elif exc_cls is not None:
            QMessageBox.warning(self, "Parsing Error", message)
        else:
            QMessageBox.critical(self, "Unexpected Error", message)

    def _on_parse_error_if_current(self, err_type, message):
        """Suppress errors from a worker invalidated by newer fragment input."""
        if self._worker is not None and self._worker.request_token == self._request_token:
            self._on_parse_error(err_type, message)

    def _on_worker_finished(self):
        """Re-enable button after worker completes (success or error)."""
        self.btn_plot.setEnabled(True)
        set_translated_text(self.btn_plot, "\U0001f52c Generate Hybridization Plot")

    # ---------- rendering (main thread only) ----------

    def _get_theme_dict_for_n(self, n):
        if n <= 2: return THEMES_CONFIG.get("2_color", {})
        elif n == 3: return THEMES_CONFIG.get("3_color", {})
        elif n == 4: return THEMES_CONFIG.get("4_color", {})
        elif n == 5: return THEMES_CONFIG.get("5_color_dos", {})
        else: return THEMES_CONFIG.get("multi_color", {})

    def _on_overlap_theme_changed(self):
        """Change only the overlap and fragments explicitly following it."""
        self.state.hybridization_style["overlap"] = combo_value(self.combo_theme_top)
        self._on_setting_changed()

    def _set_all_center_visibility(self, state):
        """Apply the prominent global d-band-center switch to every panel."""
        if state == Qt.PartiallyChecked.value:
            return
        checked = state == Qt.Checked.value
        for center_check in (
            self.chk_center_top, self.chk_center_mid, self.chk_center_bot,
        ):
            center_check.blockSignals(True)
            center_check.setChecked(checked)
            center_check.blockSignals(False)
        self._on_setting_changed()

    def _sync_global_center_visibility(self):
        """Reflect independent per-panel switches in the global control."""
        states = [
            check.isChecked() for check in (
                self.chk_center_top, self.chk_center_mid, self.chk_center_bot,
            )
        ]
        if all(states):
            global_state = Qt.Checked
        elif any(states):
            global_state = Qt.PartiallyChecked
        else:
            global_state = Qt.Unchecked
        self.chk_centers_all.blockSignals(True)
        self.chk_centers_all.setCheckState(global_state)
        self.chk_centers_all.blockSignals(False)
        self._on_setting_changed()

    @staticmethod
    def _coordinated_fragment_colors(base_color, count):
        """Return a smooth, related palette anchored to an Overlap color."""
        if count <= 1:
            return [base_color]

        base = np.asarray(to_rgb(base_color))
        white = np.ones(3)
        # Start with the exact overlap color, then move gradually toward
        # lighter tints.  The aggregate curve and orbital decomposition read
        # as one fragment without making multiple orbitals indistinguishable.
        tint_amounts = np.linspace(0.0, 0.55, count)
        colors = []
        for tint_amount in tint_amounts:
            rgb = base * (1.0 - tint_amount) + white * tint_amount
            colors.append(to_hex(np.clip(rgb, 0.0, 1.0)))
        return colors

    _DEFAULT_ORBITAL_THEME = "Default orbital colors"

    def _fragment_style(self, index):
        return self.state.hybridization_style.setdefault(str(index), {})

    def _save_fragment_style(self, index):
        combo = (self.combo_theme_mid, self.combo_theme_bot)[index]
        self._fragment_style(index)["theme"] = combo_value(combo)
        self._on_setting_changed()

    def _add_color_controls(self, layout, index):
        for title, callback in (
            ("Orbital colors…", lambda: self._show_orbital_colors(index)),
            ("Import main PDOS colors", lambda: self._import_pdos_colors(index)),
            ("Restore default colors", lambda: self._reset_fragment_colors(index)),
        ):
            button = QPushButton(title)
            button.clicked.connect(callback)
            layout.addWidget(button)
        check = QCheckBox("Fill total curves")
        check.setToolTip(tr("Fill totals alongside components"))
        check.setChecked(bool(self._fragment_style(index).get("fill_totals", False)))
        check.toggled.connect(lambda value: self._set_total_fill(index, value))
        layout.addWidget(check)
        setattr(self, f"_total_fill_{index}", check)

    def _set_total_fill(self, index, value):
        self._fragment_style(index)["fill_totals"] = value
        self._on_setting_changed()

    def _import_pdos_colors(self, index):
        overrides = self._fragment_style(index).setdefault("colors", {})
        for orb in d_orb_names:
            color = self.state.orb_colors.get(orb)
            if isinstance(color, str) and QColor(color).isValid():
                overrides[orb] = color
        self._on_setting_changed()

    def _reset_fragment_colors(self, index):
        self._fragment_style(index).clear()
        combo = (self.combo_theme_mid, self.combo_theme_bot)[index]
        set_combo_value(combo, self._DEFAULT_ORBITAL_THEME)
        getattr(self, f"_total_fill_{index}").setChecked(False)
        self._on_setting_changed()

    def _fragment_color_map(self, index):
        # Stable identities: neither selection order nor totals consume colors.
        style = self._fragment_style(index)
        selected = style.get("theme", self._DEFAULT_ORBITAL_THEME)
        top = THEMES_CONFIG.get("2_color", {}).get(
            combo_value(self.combo_theme_top), [HYB_FRAG1_COLOR, HYB_FRAG2_COLOR])
        colors = {"s": "#607D8B", "p": top[index], "d": top[index], "f": "#795548"}
        groups = (p_orb_names, d_orb_names, f_orb_names)
        palettes = (
            THEMES_CONFIG["3_color"]["Spring (Red-Yellow-Mint)"],
            THEMES_CONFIG["5_color_dos"]["Distinct Categorical"],
            DECOMP_COLORS[5:12],
        )
        theme_palette = next((group[selected] for group in THEMES_CONFIG.values()
                              if selected in group), None)
        following = selected in (self._FOLLOW_OVERLAP_FRAG1, self._FOLLOW_OVERLAP_FRAG2)
        for orbitals, default in zip(groups, palettes):
            palette = (self._coordinated_fragment_colors(top[index], len(orbitals))
                       if following else theme_palette or default)
            colors.update({orb: palette[i % len(palette)] for i, orb in enumerate(orbitals)})
        for orb, color in style.get("colors", {}).items():
            if orb in colors and isinstance(color, str) and QColor(color).isValid():
                colors[orb] = color
        return colors

    def _show_orbital_colors(self, index):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Orbital colors…"))
        layout = QVBoxLayout(dialog)
        panel = (self.frag1, self.frag2)[index]
        orbitals = panel.get_selected_orbitals()
        if not orbitals:
            layout.addWidget(QLabel(tr("Select orbitals in the Fragment tab first.")))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        rows = QVBoxLayout(content)
        for orb in orbitals:
            button = QPushButton()
            def refresh(btn=button, name=orb):
                color = self._fragment_color_map(index)[name]
                label = f"{name}-total" if name in ("s", "p", "d", "f") else format_orbital_display(name)
                btn.setText(f"{label}  {color}")
                c = QColor(color)
                foreground = "#000000" if c.lightnessF() > 0.55 else "#FFFFFF"
                btn.setStyleSheet(f"background-color: {color}; color: {foreground}; padding: 6px;")
            def pick(_checked=False, name=orb, update=refresh):
                color = QColorDialog.getColor(QColor(self._fragment_color_map(index)[name]), dialog, name)
                if color.isValid():
                    self._fragment_style(index).setdefault("colors", {})[name] = color.name()
                    update()
                    self._on_setting_changed()
            refresh()
            button.clicked.connect(pick)
            rows.addWidget(button)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        close = QPushButton(tr("Close"))
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.resize(320, 420)
        dialog.exec()

    def _update_fragment_themes(self, combo, orbital_count, follow_label):
        index = 0 if follow_label == self._FOLLOW_OVERLAP_FRAG1 else 1
        current = self._fragment_style(index).get("theme", self._DEFAULT_ORBITAL_THEME)
        names = list(dict.fromkeys(name for group in THEMES_CONFIG.values() for name in group))
        combo.blockSignals(True)
        combo.clear()
        combo.addItems([self._DEFAULT_ORBITAL_THEME, follow_label] + names)
        combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        combo.setMinimumWidth(0)
        set_combo_value(combo, current if current in names + [follow_label] else self._DEFAULT_ORBITAL_THEME)
        combo.blockSignals(False)
        get_language_manager().apply(combo)

    def _update_mid_themes(self):
        n = len(self.frag1.get_selected_orbitals())
        self._update_fragment_themes(
            self.combo_theme_mid, n, self._FOLLOW_OVERLAP_FRAG1)
        self._on_setting_changed()

    def _update_bot_themes(self):
        n = len(self.frag2.get_selected_orbitals())
        self._update_fragment_themes(
            self.combo_theme_bot, n, self._FOLLOW_OVERLAP_FRAG2)
        self._on_setting_changed()

    def _sync_x_ranges(self):
        """Sync the X-range from Overlap tab to all other tabs."""
        xmin, xmax = self.x_range_top.get_range()
        self.x_range_mid.set_range(xmin, xmax)
        self.x_range_bot.set_range(xmin, xmax)
        self._on_setting_changed()

    def _autoscale_y_for_x_range(self, ax, x_min, x_max, data_list=None):
        """Automatically scale Y axis based only on visible data within X range."""
        if x_min is None or x_max is None or data_list is None:
            return

        from utils.helpers import get_y_limits_for_x_range
        y_min = float('inf')
        y_max = float('-inf')

        for x_arr, y_arrs in data_list:
            ymin_c, ymax_c = get_y_limits_for_x_range(x_arr, y_arrs, x_min, x_max)
            y_min = min(y_min, ymin_c)
            y_max = max(y_max, ymax_c)

        if y_min != float('inf') and y_max != float('-inf'):
            padding = (y_max - y_min) * 0.05
            if padding == 0:
                padding = y_max * 0.05 if y_max > 0 else 0.1
            ax.set_ylim(y_min - padding, y_max + padding)

    def _render_plot(self, data1, data2):
        """Render the 3-subplot hybridization figure (main thread, ~10ms).

        Args:
            data1: (e_aligned, rho_up, rho_dn, orbitals, label) for fragment 1
            data2: (e_aligned, rho_up, rho_dn, orbitals, label) for fragment 2
        """
        e1, rho1_up, rho1_dn, orbs1, label1 = data1
        e2, rho2_up, rho2_dn, orbs2, label2 = data2
        atoms1 = self._batch_display[0] if self._batch_display else self.frag1.get_atoms_text().strip()
        atoms2 = self._batch_display[1] if self._batch_display else self.frag2.get_atoms_text().strip()
        display1 = f"{label1} [Atoms: {atoms1}]" if atoms1 else label1
        display2 = f"{label2} [Atoms: {atoms2}]" if atoms2 else label2
        aggregate_orbs1 = non_overlapping_orbitals(orbs1)
        aggregate_orbs2 = non_overlapping_orbitals(orbs2)

        # Merge for export CSV
        rho1_export = {}
        for o in orbs1:
            u = rho1_up.get(o, np.zeros_like(e1)) if rho1_up else 0
            d = rho1_dn.get(o, np.zeros_like(e1)) if rho1_dn else 0
            rho1_export[o] = u + d
        rho2_export = {}
        for o in orbs2:
            u = rho2_up.get(o, np.zeros_like(e2)) if rho2_up else 0
            d = rho2_dn.get(o, np.zeros_like(e2)) if rho2_dn else 0
            rho2_export[o] = u + d

        self._plot_e1, self._plot_rho1, self._plot_orbs1, self._plot_label1 = e1, rho1_export, orbs1, display1
        self._plot_e2, self._plot_rho2, self._plot_orbs2, self._plot_label2 = e2, rho2_export, orbs2, display2

        show_center_top = self.chk_center_top.isChecked()
        show_center_mid = self.chk_center_mid.isChecked()
        show_center_bot = self.chk_center_bot.isChecked()

        x_min_top, x_max_top = self.x_range_top.get_range()
        y_min_top, y_max_top = self.y_range_top.get_range()
        x_min_mid, x_max_mid = self.x_range_mid.get_range()
        y_min_mid, y_max_mid = self.y_range_mid.get_range()
        x_min_bot, x_max_bot = self.x_range_bot.get_range()
        y_min_bot, y_max_bot = self.y_range_bot.get_range()

        # Resolve themes and colors
        t_top = combo_value(self.combo_theme_top)
        colors_top = THEMES_CONFIG.get("2_color", {}).get(t_top, [HYB_FRAG1_COLOR, HYB_FRAG2_COLOR])
        overlap_frag1 = colors_top[0] if len(colors_top) > 0 else HYB_FRAG1_COLOR
        overlap_frag2 = colors_top[1] if len(colors_top) > 1 else HYB_FRAG2_COLOR

        colors_mid = self._fragment_color_map(0)
        colors_bot = self._fragment_color_map(1)
        c_frag1, c_frag2 = overlap_frag1, overlap_frag2

        lw = self.spin_lw.value()
        do_fill = self.chk_fill.isChecked()
        fill_alpha = self.spin_alpha.value()

        # ── Clear axes content without destroying the axes objects ──
        # Persistent axes (created in _build_ui) eliminate the
        # clear→subplots→tight_layout instability cycle.
        # Root cause fix: Instead of ax.cla() which clears labels and limit settings,
        # we specifically remove the drawn elements. This is faster and avoids layout recalculation jitter.
        for ax in (self._ax_top, self._ax_mid, self._ax_bot):
            while ax.lines:
                ax.lines[0].remove()
            while ax.collections:
                ax.collections[0].remove()
            while ax.texts:
                ax.texts[0].remove()
            if ax.get_legend() is not None:
                ax.get_legend().remove()
            ax.relim()
            ax.autoscale_view()
            ax.set_prop_cycle(None)

        # Helper to plot mirror lines
        def plot_spin(ax, e, r_up, r_dn, orbs, color, label, fill=False):
            t_up = np.zeros_like(e)
            t_dn = np.zeros_like(e)
            for o in orbs:
                if r_up: t_up += r_up.get(o, np.zeros_like(e))
                if r_dn: t_dn += r_dn.get(o, np.zeros_like(e))

            if r_up and r_dn:
                if fill:
                    ax.fill_between(e, t_up, alpha=fill_alpha, color=color)
                    ax.fill_between(e, -t_dn, alpha=fill_alpha, color=color)
                ax.plot(e, t_up, color=color, lw=lw, label=label)
                ax.plot(e, -t_dn, color=color, lw=lw, ls="--")
            elif r_up:
                if fill: ax.fill_between(e, t_up, alpha=fill_alpha, color=color)
                ax.plot(e, t_up, color=color, lw=lw, label=label)
            elif r_dn:
                if fill: ax.fill_between(e, -t_dn, alpha=fill_alpha, color=color)
                ax.plot(e, -t_dn, color=color, lw=lw, label=label)

        def _plot_fragment_decomposition(ax, e, rho_up, rho_dn, orbs, colors, label_title, fragment_index):
            for o in orbs:
                c = colors[o]
                components = {"p": p_orb_names, "d": d_orb_names, "f": f_orb_names}.get(o, ())
                mixed_total = any(child in orbs for child in components)
                curve_lw = lw * 1.5 if mixed_total else lw
                curve_fill = do_fill and (not mixed_total or self._fragment_style(fragment_index).get("fill_totals", False))
                curve_label = f"{o}-total" if o in ("s", "p", "d", "f") else format_orbital_display(o)
                d_up = rho_up.get(o, np.zeros_like(e)) if rho_up else None
                d_dn = rho_dn.get(o, np.zeros_like(e)) if rho_dn else None
                if rho_up and rho_dn:
                    if curve_fill:
                        ax.fill_between(e, d_up, alpha=fill_alpha, color=c)
                        ax.fill_between(e, -d_dn, alpha=fill_alpha, color=c)
                    ax.plot(e, d_up, lw=curve_lw, color=c, label=curve_label)
                    ax.plot(e, -d_dn, lw=curve_lw, color=c, ls="--")
                elif rho_up:
                    if curve_fill: ax.fill_between(e, d_up, alpha=fill_alpha, color=c)
                    ax.plot(e, d_up, lw=curve_lw, color=c, label=curve_label)
                elif rho_dn:
                    if curve_fill: ax.fill_between(e, -d_dn, alpha=fill_alpha, color=c)
                    ax.plot(e, -d_dn, lw=curve_lw, color=c, label=curve_label)
            zero_color = "#666666" if self._is_dark_mode else "black"
            ax.axhline(0, color=zero_color, lw=0.4, zorder=0)
            ax.axvline(0, color='gray', ls="--", lw=0.6, zorder=0)
            ax.set_ylabel("DOS")
            ax.set_title(label_title, fontsize=9, loc="left")
            spin_mode = self._batch_display[2] if self._batch_display else self._get_spin_mode()
            leg_loc = "lower right" if spin_mode == "down" else "upper right"
            ax.legend(fontsize=8, ncol=5, loc=leg_loc, frameon=False)

        # ═══ Step 1: Draw all data first ═══
        ax_top = self._ax_top
        plot_spin(ax_top, e1, rho1_up, rho1_dn, aggregate_orbs1, c_frag1, f"{display1} ({'+'.join(aggregate_orbs1)})", fill=do_fill)
        plot_spin(ax_top, e2, rho2_up, rho2_dn, aggregate_orbs2, c_frag2, f"{display2} ({'+'.join(aggregate_orbs2)})", fill=do_fill)
        
        zero_color = "#666666" if self._is_dark_mode else "black"
        ax_top.axhline(0, color=zero_color, lw=0.4, zorder=0)
        ax_top.axvline(0, color="gray", ls="--", lw=0.6, zorder=0)
        ax_top.set_ylabel("DOS")
        ax_top.set_title(tr("Hybridization Overlap"), fontsize=10, loc="left")
        spin_mode = self._batch_display[2] if self._batch_display else self._get_spin_mode()
        leg_loc = "lower right" if spin_mode == "down" else "upper right"
        ax_top.legend(fontsize=9, loc=leg_loc, frameon=False)

        _plot_fragment_decomposition(
            self._ax_mid, e1, rho1_up, rho1_dn, orbs1, colors_mid,
            tr(f"Fragment 1: {display1}"), 0)
        _plot_fragment_decomposition(
            self._ax_bot, e2, rho2_up, rho2_dn, orbs2, colors_bot,
            tr(f"Fragment 2: {display2}"), 1)

        # ═══ Step 2: Autoscale to compute natural Y limits from data ═══
        ax_top.autoscale_view()
        self._ax_mid.autoscale_view()
        self._ax_bot.autoscale_view()

        # ═══ Step 3: Apply user-specified ranges (overrides autoscale) ═══
        def _sum_orbs(r, orbs, e):
            if not r: return None
            res = np.zeros_like(e)
            for o in orbs:
                res += r.get(o, np.zeros_like(e))
            return res

        if x_min_top is not None and x_max_top is not None:
            ax_top.set_xlim(x_min_top, x_max_top)
            if y_min_top is None or y_max_top is None:
                data_list_top = []
                if e1 is not None:
                    data_list_top.append((e1, [_sum_orbs(rho1_up, aggregate_orbs1, e1),
                                               -_sum_orbs(rho1_dn, aggregate_orbs1, e1) if rho1_dn else None]))
                if e2 is not None:
                    data_list_top.append((e2, [_sum_orbs(rho2_up, aggregate_orbs2, e2),
                                               -_sum_orbs(rho2_dn, aggregate_orbs2, e2) if rho2_dn else None]))
                self._autoscale_y_for_x_range(ax_top, x_min_top, x_max_top, data_list=data_list_top)
        if y_min_top is not None and y_max_top is not None:
            ax_top.set_ylim(y_min_top, y_max_top)
            
        if x_min_mid is not None and x_max_mid is not None:
            self._ax_mid.set_xlim(x_min_mid, x_max_mid)
            if y_min_mid is None or y_max_mid is None:
                data_list_mid = []
                if e1 is not None:
                    y_arrs = []
                    for o in orbs1:
                        if rho1_up: y_arrs.append(rho1_up.get(o, np.zeros_like(e1)))
                        if rho1_dn: y_arrs.append(-rho1_dn.get(o, np.zeros_like(e1)))
                    data_list_mid.append((e1, y_arrs))
                self._autoscale_y_for_x_range(self._ax_mid, x_min_mid, x_max_mid, data_list=data_list_mid)
        if y_min_mid is not None and y_max_mid is not None:
            self._ax_mid.set_ylim(y_min_mid, y_max_mid)
            
        if x_min_bot is not None and x_max_bot is not None:
            self._ax_bot.set_xlim(x_min_bot, x_max_bot)
            if y_min_bot is None or y_max_bot is None:
                data_list_bot = []
                if e2 is not None:
                    y_arrs = []
                    for o in orbs2:
                        if rho2_up: y_arrs.append(rho2_up.get(o, np.zeros_like(e2)))
                        if rho2_dn: y_arrs.append(-rho2_dn.get(o, np.zeros_like(e2)))
                    data_list_bot.append((e2, y_arrs))
                self._autoscale_y_for_x_range(self._ax_bot, x_min_bot, x_max_bot, data_list=data_list_bot)
        if y_min_bot is not None and y_max_bot is not None:
            self._ax_bot.set_ylim(y_min_bot, y_max_bot)

        # ═══ Step 4: Compute band centers ═══
        c1 = c2 = None
        limit_fermi, custom_range, range_str = self._get_integration_limits()

        if show_center_top or show_center_mid:
            c1, _, _, _ = calc_metrics(e1, rho1_export, ef=0.0,
                                        orb_names=aggregate_orbs1,
                                        limit_fermi=limit_fermi,
                                        custom_range=custom_range,
                                        method=self._integration_method)
        if show_center_top or show_center_bot:
            c2, _, _, _ = calc_metrics(e2, rho2_export, ef=0.0,
                                        orb_names=aggregate_orbs2,
                                        limit_fermi=limit_fermi,
                                        custom_range=custom_range,
                                        method=self._integration_method)

        # ═══ Step 5: Draw center annotations LAST (after ranges are final) ═══
        if show_center_top:
            hyb_name = f"{display1}-{display2}"
            y_off = 0
            if c1 is not None and not np.isnan(c1):
                y_off = annotate_center(ax_top, c1, f"\u03b5({hyb_name}, {range_str})", HYB_METAL_CENTER_COLOR, CENTER_LW, CENTER_FONTSIZE, y_off)
            if c2 is not None and not np.isnan(c2):
                y_off = annotate_center(ax_top, c2, f"\u03b5({hyb_name}, {range_str})", HYB_LIGAND_CENTER_COLOR, CENTER_LW, CENTER_FONTSIZE, y_off)
        if show_center_mid and c1 is not None and not np.isnan(c1):
            annotate_center(self._ax_mid, c1, f"\u03b5({display1}, {range_str})", HYB_METAL_CENTER_COLOR, CENTER_LW, CENTER_FONTSIZE)
        if show_center_bot and c2 is not None and not np.isnan(c2):
            annotate_center(self._ax_bot, c2, f"\u03b5({display2}, {range_str})", HYB_LIGAND_CENTER_COLOR, CENTER_LW, CENTER_FONTSIZE)

        # ═══ Labels & title (constrained_layout handles spacing) ═══
        ax_top.set_xlabel(r"E - E$_{f}$ (eV)")
        self._ax_mid.set_xlabel(r"E - E$_{f}$ (eV)")
        self._ax_bot.set_xlabel(r"E - E$_{f}$ (eV)")
        self.fig.suptitle(
            tr(f"Orbital Hybridization: {display1} vs {display2}"), fontsize=11)
        self._apply_dark_mode()
        self.canvas.draw()

    # ---------- export ----------

    def _export_csv(self):
        if not self._has_plot_data:
            QMessageBox.warning(self, "Warning", "Generate a plot first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Hybridization Data",
                                              "hybridization_data.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            DataExporter.export_hybridization_csv(
                self._plot_e1, self._plot_rho1, self._plot_orbs1, self._plot_label1,
                self._plot_e2, self._plot_rho2, self._plot_orbs2, self._plot_label2,
                path)
        except OSError as e:
            QMessageBox.critical(self, "Export Failed", f"Cannot write CSV:\n{e}")
            return
        QMessageBox.information(self, "Success", f"Data exported to:\n{path}")

    def _save_png(self):
        if not self._has_plot_data:
            QMessageBox.warning(self, "Warning", "Generate a plot first.")
            return
        try:
            initial_dir = ensure_export_directory(self.state.file_entries)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export Folder Error",
                f"Cannot open the preferred export folder:\n{exc}")
            return
        initial_path = initial_dir / "hybridization_chart.png"
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Hybridization Chart", str(initial_path),
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if not path:
            return
        selected_format = next(
            (name.lower() for name in ("PNG", "PDF", "SVG")
             if selected_filter.startswith(name)), "png")
        output_path = selected_export_path(path, selected_format)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            DataExporter.save_figure(self.fig, str(output_path))
        except OSError as exc:
            QMessageBox.critical(
                self, "Save Failed", f"Cannot save chart:\n{exc}")
            return
        remember_export_directory(output_path.parent)
        QMessageBox.information(
            self, "Success", f"Chart saved to:\n{output_path}")

    def set_dark_mode(self, is_dark):
        self._is_dark_mode = is_dark
        
        # Apply dark mode to sub-components manually if needed
        from ui.theme_macos import LIGHT_GLASS_QSS, DARK_GLASS_QSS
        qss = DARK_GLASS_QSS if is_dark else LIGHT_GLASS_QSS
        self.setStyleSheet(localized_stylesheet(qss))
        self._apply_dark_mode()

    def set_integration_method(self, method: str):
        """Set the numerical integration method for center annotations."""
        self._integration_method = method
        idx = find_combo_value(self.combo_integ_method, method)
        if idx >= 0:
            self.combo_integ_method.blockSignals(True)
            self.combo_integ_method.setCurrentIndex(idx)
            self.combo_integ_method.blockSignals(False)
        if self._cached_data:
            self._render_plot(*self._cached_data)

    def _apply_dark_mode(self):
        if not self.fig.axes:
            bg_color = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
            self.fig.patch.set_facecolor(bg_color)
            self.canvas.draw()
            return

        bg_color = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
        fg_color = "#E0E0E0" if self._is_dark_mode else "black"

        self.fig.patch.set_facecolor(bg_color)
        self.fig.suptitle(self.fig._suptitle.get_text() if self.fig._suptitle else "", color=fg_color)
        
        for ax in [self._ax_top, self._ax_mid, self._ax_bot]:
            ax.set_facecolor(bg_color)
            ax.tick_params(colors=fg_color, which='both')
            for spine in ax.spines.values():
                spine.set_color(fg_color)
                
            ax.xaxis.label.set_color(fg_color)
            ax.yaxis.label.set_color(fg_color)
            for t in [ax.title, getattr(ax, '_left_title', None), getattr(ax, '_right_title', None)]:
                if t is not None:
                    t.set_color(fg_color)
            
            for text in ax.texts:
                bbox = text.get_bbox_patch()
                if bbox is not None:
                    bbox.set_facecolor(bg_color)
                    bbox.set_edgecolor("none")
                if text.get_color() != HYB_METAL_CENTER_COLOR and text.get_color() != HYB_LIGAND_CENTER_COLOR:
                    # flip explicit black text in dark mode
                    if self._is_dark_mode:
                        c = text.get_color()
                        if c == '#000000' or c == 'black' or c == (0.0, 0.0, 0.0, 1.0):
                            text.set_color('#E0E0E0')
                    else:
                        text.set_color(fg_color)

            leg = ax.get_legend()
            if leg:
                frame = leg.get_frame()
                frame.set_facecolor(bg_color)
                frame.set_edgecolor(fg_color)
                for text in leg.get_texts():
                    text.set_color(fg_color)
                    
        self.canvas.draw()
