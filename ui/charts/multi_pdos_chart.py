"""
Matplotlib-based Multi-System PDOS comparison chart widget.
Allows plotting multiple systems' specific orbitals or total d-DOS overlaid.
"""
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
import matplotlib.cm as cm
import matplotlib.colors as mcolors

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QColorDialog, QMessageBox, QMenu
)
from PySide6.QtGui import QColor, QAction
from PySide6.QtCore import Qt, Signal

from core.parsers.constants import d_orb_names
from core.calculator import calc_metrics, _integrate
from utils.styling import THEMES_CONFIG, CENTER_COLOR, CENTER_LW, CENTER_FONTSIZE
from utils.helpers import format_orbital_display
from ui.widgets.axes_config_dialog import AxesConfigDialog
from ui.charts.multi_pdos_chart_dialogs import MultiPDOSDataDialog, MultiPDOSStyleDialog

class MultiPDOSChartWidget(QWidget):
    """Matplotlib-based Multi-System PDOS chart widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parsed_cache = {}
        self._results_data = []
        self._system_colors = {}
        self._is_dark_mode = False
        self.axes_config = None
        self._integration_method = "trapezoid"
        
        # Color palettes
        self._default_palette = [mcolors.to_hex(c) for c in cm.tab10.colors]
        
        self._init_matplotlib()
        self._build_ui()
        
    def _init_matplotlib(self):
        """Initialize matplotlib rcParams for consistent styling."""
        import matplotlib
        matplotlib.rcParams['font.family'] = 'serif'
        matplotlib.rcParams['font.serif'] = ['Times New Roman', 'SimSun', 'Arial Unicode MS', 'DejaVu Serif']
        matplotlib.rcParams['mathtext.fontset'] = 'stix'
        matplotlib.rcParams['axes.unicode_minus'] = False
        matplotlib.rcParams['axes.linewidth'] = 1.0
        matplotlib.rcParams['axes.labelsize'] = 11
        matplotlib.rcParams['axes.titlesize'] = 11
        matplotlib.rcParams['xtick.labelsize'] = 10
        matplotlib.rcParams['ytick.labelsize'] = 10
        matplotlib.rcParams['legend.fontsize'] = 9
        matplotlib.rcParams['figure.constrained_layout.use'] = True
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # Instantiate floating dialogs
        self.data_dlg = MultiPDOSDataDialog(self)
        self.style_dlg = MultiPDOSStyleDialog(self)
        self.axes_dlg = AxesConfigDialog(current_config=self.axes_config, parent=self)
        
        # Connect Apply buttons and real-time signals to redraw
        self.data_dlg.applied.connect(self._on_redraw_request)
        self.data_dlg.real_time_update.connect(self._on_redraw_request)
        self.style_dlg.applied.connect(self._on_redraw_request)
        self.style_dlg.real_time_update.connect(self._on_redraw_request)
        self.axes_dlg.applied.connect(self._on_axes_applied)
        self.axes_dlg.real_time_update.connect(self._on_axes_applied)
        
        # Style connects
        self.style_dlg.btn_colors.clicked.connect(self._show_color_menu)
        
        # Toolbar widget (embedded in MainWindow corner)
        self.toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(self.toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(4)
        
        btn_data = QPushButton("📊 Data")
        btn_data.clicked.connect(self.data_dlg.show)
        toolbar_layout.addWidget(btn_data)
        
        btn_style = QPushButton("🎨 Style")
        btn_style.clicked.connect(self.style_dlg.show)
        toolbar_layout.addWidget(btn_style)
        
        btn_axes = QPushButton("⚙️ Axes")
        btn_axes.clicked.connect(self.axes_dlg.show)
        toolbar_layout.addWidget(btn_axes)

        
        # Matplotlib Figure and Canvas
        self.fig = Figure(constrained_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.hide()
        self.toolbar.zoom()
        
        # Wrap canvas in a horizontal layout to add margins
        canvas_layout = QHBoxLayout()
        canvas_layout.setContentsMargins(50, 0, 50, 10)
        canvas_layout.addWidget(self.canvas)
        layout.addLayout(canvas_layout)
        
        self._ax = None
        
    def _on_axes_applied(self):
        self.axes_config = self.axes_dlg.get_config()
        self._on_redraw_request()
            
    def _show_color_menu(self):
        """Show a menu to pick colors for each system."""
        labels = self.data_dlg.combo_systems.get_checked_items()
        if not labels:
            QMessageBox.information(self, "Colors", "No systems selected.")
            return
            
        menu = QMenu(self)
        for label in labels:
            action = QAction(f"Set color for {label}...", self)
            # Use lambda default argument to capture current label
            action.triggered.connect(lambda checked, lbl=label: self._set_system_color(lbl))
            menu.addAction(action)
        
        menu.exec(self.style_dlg.btn_colors.mapToGlobal(self.style_dlg.btn_colors.rect().bottomLeft()))

    def _set_system_color(self, label):
        """Open color dialog for a specific system."""
        current_hex = self._system_colors.get(label, "#000000")
        color = QColorDialog.getColor(QColor(current_hex), self, f"Pick Color for {label}")
        if color.isValid():
            self._system_colors[label] = color.name()
            self._on_redraw_request()

    def update_data(self, parsed_cache, results_data):
        """Update available systems and redraw."""
        self._parsed_cache = parsed_cache
        self._results_data = results_data
        
        self.data_dlg.combo_systems.blockSignals(True)
        # Remember currently checked items
        prev_checked = set(self.data_dlg.combo_systems.get_checked_items())
        
        self.data_dlg.combo_systems.clear_items()
        
        labels = []
        seen = set()
        for rd in results_data:
            if rd.label in parsed_cache and rd.label not in seen:
                labels.append(rd.label)
                seen.add(rd.label)
                
        # Assign colors for new systems
        for i, lbl in enumerate(labels):
            if lbl not in self._system_colors:
                self._system_colors[lbl] = self._default_palette[i % len(self._default_palette)]
        
        for lbl in labels:
            # Check if it was previously checked, or if it's new, check by default
            is_checked = (lbl in prev_checked) if prev_checked else True
            self.data_dlg.combo_systems.add_item(lbl, checked=is_checked)
            
        self.data_dlg.combo_systems.blockSignals(False)
        
        # Update center ref combo
        self._update_center_ref_combo()
        
        self._on_redraw_request()
        
    def _update_center_ref_combo(self):
        self.data_dlg.combo_center_ref.blockSignals(True)
        curr_ref = self.data_dlg.combo_center_ref.currentText()
        self.data_dlg.combo_center_ref.clear()
        self.data_dlg.combo_center_ref.addItem("All Selected Systems")
        
        checked_labels = self.data_dlg.combo_systems.get_checked_items()
        for lbl in checked_labels:
            self.data_dlg.combo_center_ref.addItem(lbl)
            
        # Restore selection if possible
        idx = self.data_dlg.combo_center_ref.findText(curr_ref)
        if idx >= 0:
            self.data_dlg.combo_center_ref.setCurrentIndex(idx)
        else:
            self.data_dlg.combo_center_ref.setCurrentIndex(0)
        self.data_dlg.combo_center_ref.blockSignals(False)

    def _on_redraw_request(self):
        """Redraw plot with current settings."""
        self._update_center_ref_combo()
        self.draw_plot()
            
    def clear_chart(self):
        """Clear the chart and data."""
        self._parsed_cache = {}
        self._results_data = []
        self._system_colors = {}
        self.data_dlg.combo_systems.clear_items()
        self.fig.clear()
        self._ax = None
        self.canvas.draw()
        
    def draw_plot(self):
        """Draw Multi-System PDOS plot with Matplotlib."""
        self.fig.clear()
        self._ax = self.fig.add_subplot(111)
        self._annot_y = 0.95
        
        selected_labels = self.data_dlg.combo_systems.get_checked_items()
        if not selected_labels:
            self.canvas.draw()
            return
            
        orbital_target = self.data_dlg.combo_orbital.currentText()
        spin_mode = self.data_dlg.combo_spin_mode.currentText()
        
        lw = self.style_dlg.spin_lw.value()
        do_fill = self.style_dlg.chk_fill.isChecked()
        alpha = self.style_dlg.spin_alpha.value()
        show_center = self.data_dlg.chk_show_center.isChecked()
        center_ref = self.data_dlg.combo_center_ref.currentText()
        
        for label in selected_labels:
            if label not in self._parsed_cache:
                continue
                
            cache_entry = self._parsed_cache[label]
            hex_color = self._system_colors.get(label, "#000000")
            
            e_raw = cache_entry["energy"]
            ef = cache_entry.get("ef", 0.0)
            e = e_raw - ef
            
            rho_up = cache_entry["up"]
            rho_dn = cache_entry["down"]
            has_spin = cache_entry["has_spin"]
            
            if not has_spin and spin_mode in ["Spin Up", "Spin Down"]:
                continue # Skip if requested spin is missing
                
            # Extract relevant DOS
            dos_up = self._extract_dos(rho_up, orbital_target, len(e))
            if has_spin:
                dos_dn = self._extract_dos(rho_dn, orbital_target, len(e))
            else:
                dos_dn = None
                
            # Plot
            if spin_mode == "Total (Up+Down)":
                self._ax.plot(e, dos_up, color=hex_color, lw=lw, label=label)
                if do_fill:
                    self._ax.fill_between(e, 0, dos_up, color=hex_color, alpha=alpha, zorder=1)
                    
                if dos_dn is not None:
                    # Spin Down goes to negative Y
                    self._ax.plot(e, -dos_dn, color=hex_color, lw=lw, label=None) # No double legend
                    if do_fill:
                        self._ax.fill_between(e, 0, -dos_dn, color=hex_color, alpha=alpha, zorder=1)
                        
            elif spin_mode == "Spin Up":
                self._ax.plot(e, dos_up, color=hex_color, lw=lw, label=label)
                if do_fill:
                    self._ax.fill_between(e, 0, dos_up, color=hex_color, alpha=alpha, zorder=1)
                    
            elif spin_mode == "Spin Down":
                if dos_dn is not None:
                    # In Spin Down ONLY mode, standard practice is to plot it positive for easier reading
                    self._ax.plot(e, dos_dn, color=hex_color, lw=lw, label=label)
                    if do_fill:
                        self._ax.fill_between(e, 0, dos_dn, color=hex_color, alpha=alpha, zorder=1)
            
            # Draw Center
            if show_center:
                if center_ref == "All Selected Systems" or center_ref == label:
                    # For center, if mode is Total and there's down spin, we need the sum for accurate center.
                    if spin_mode == "Spin Down" and dos_dn is not None:
                        calc_dos = dos_dn
                    else:
                        calc_dos = dos_up
                        if spin_mode == "Total (Up+Down)" and dos_dn is not None:
                            calc_dos = dos_up + dos_dn
                            
                    self._draw_center_annotation(e, calc_dos, label, hex_color)

        self._ax.set_xlabel("E − E$_{f}$ (eV)")
        self._ax.set_ylabel("DOS")
        
        title_target = orbital_target if orbital_target != "Total d-DOS" else "Total d"
        self._ax.set_title(f"Multi-System {title_target} PDOS Comparison ({spin_mode})", fontsize=10, loc='left', pad=6)
            
        # Apply axes limits
        c = self.axes_config or {}
        x_min, x_max = c.get("x_min"), c.get("x_max")
        y_min, y_max = c.get("y_min"), c.get("y_max")
        
        if x_min is not None and x_max is not None:
            self._ax.set_xlim(x_min, x_max)
        if y_min is not None and y_max is not None:
            self._ax.set_ylim(y_min, y_max)
                
        self._apply_axes_style()
        self._apply_dark_mode()
        self.canvas.draw()

    def set_dark_mode(self, is_dark):
        self._is_dark_mode = is_dark
        self._apply_dark_mode()

    def set_integration_method(self, method: str):
        """Set the numerical integration method for center annotation."""
        self._integration_method = method
        if self._parsed_cache:
            self._on_redraw_request()

    def _apply_dark_mode(self):
        if not self.fig.axes:
            bg_color = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
            self.fig.patch.set_facecolor(bg_color)
            self.canvas.draw()
            return

        bg_color = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
        fg_color = "#E0E0E0" if self._is_dark_mode else "black"

        self.fig.patch.set_facecolor(bg_color)
        
        ax = self._ax
        if ax:
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
                
                # If the text is explicitly black, flip it in dark mode so it remains visible
                if self._is_dark_mode:
                    c = text.get_color()
                    if c == '#000000' or c == 'black' or c == (0.0, 0.0, 0.0, 1.0):
                        text.set_color('#E0E0E0')

            leg = ax.get_legend()
            if leg:
                frame = leg.get_frame()
                frame.set_facecolor(bg_color)
                frame.set_edgecolor(fg_color)
                for text in leg.get_texts():
                    text.set_color(fg_color)
                    
        self.canvas.draw()
        
    def _extract_dos(self, rho_dict, target, length):
        """Extract requested orbital DOS or sum them up."""
        if target == "Total d-DOS":
            total = np.zeros(length)
            for o in d_orb_names:
                total += rho_dict.get(o, np.zeros(length))
            return total
        else:
            return rho_dict.get(target, np.zeros(length))

    def _apply_axes_style(self):
        """Apply consistent axes styling matching pdos_chart."""
        ax = self._ax
        c = self.axes_config or {}
        
        # Set spine visibility
        ax.spines['top'].set_visible(c.get("spine_top", True))
        ax.spines['right'].set_visible(c.get("spine_right", True))
        ax.spines['left'].set_visible(c.get("spine_left", True))
        ax.spines['bottom'].set_visible(c.get("spine_bottom", True))
        
        # Set spine linewidth
        lw = c.get("spine_lw", 1.0)
        for spine in ax.spines.values():
            spine.set_linewidth(lw)
            
        # Add grid
        if c.get("show_grid", False):
            grid_color = "#555555" if getattr(self, '_is_dark_mode', False) else "#E0E0E0"
            ax.grid(True, linestyle=":", alpha=0.6, color=grid_color, zorder=0)
        else:
            ax.grid(False)
            
        # Add zero lines
        zero_color = "#666666" if getattr(self, '_is_dark_mode', False) else "black"
        ax.axhline(0, color=zero_color, lw=0.4, zorder=0)
        ax.axvline(0, color='gray', ls='--', lw=0.6, zorder=0)
        
        # Set tick parameters strictly matching Matplotlib defaults
        tdir = c.get("tick_dir", "out")
        ax.tick_params(axis='both', which='major', direction=tdir, labelsize=10, width=lw, length=5,
                       top=False, right=False)
        ax.tick_params(axis='both', which='minor', direction=tdir, width=max(0.4, lw*0.8), length=3,
                       top=False, right=False)
                       
        # Set legend
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            ax.legend(fontsize=9, loc='upper right', frameon=False, columnspacing=1.0, handletextpad=0.4)
            
    def _draw_center_annotation(self, e, dos, label, color):
        """Draw vertical line and annotation for d-band center."""
        mask = (dos > 0) | (dos < 0) # non-zero
        if not np.any(mask): return
        
        sum_dos = _integrate(dos, e, method=self._integration_method)
        if abs(sum_dos) < 1e-8: return
        center = _integrate(e * dos, e, method=self._integration_method) / sum_dos
        
        # Add vertical dashed line
        self._ax.axvline(center, color=color, lw=1.2, ls='--', zorder=3)
        
        transform = self._ax.get_xaxis_transform()
        x_offset = (self._ax.get_xlim()[1] - self._ax.get_xlim()[0]) * 0.002
        
        self._ax.text(center + x_offset, getattr(self, '_annot_y', 0.95), f"{label}={center:.4f} eV", 
                color=color, fontsize=10,
                verticalalignment='top', horizontalalignment='left', zorder=4,
                transform=transform)
                
        self._annot_y = getattr(self, '_annot_y', 0.95) - 0.06
        
    def get_figure(self):
        """Return the matplotlib figure for export."""
        return self.fig
