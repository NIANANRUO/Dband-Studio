"""
Matplotlib-based PDOS chart widget.
Replaces PyQtGraph implementation to match Hybridization plot styling perfectly.
"""
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.gridspec import GridSpec

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QColorDialog, QMenu
)
from PySide6.QtGui import QColor, QAction
from PySide6.QtCore import Qt, Signal

from core.parsers.constants import d_orb_names
from core.calculator import calc_metrics
from utils.styling import (
    THEMES_CONFIG, CENTER_COLOR, CENTER_LW, CENTER_FONTSIZE,
    annotate_center,
)
from utils.helpers import format_orbital_display
from ui.widgets.axes_config_dialog import AxesConfigDialog
from ui.charts.pdos_chart_dialogs import PDOSDataDialog, PDOSStyleDialog

class PDOSChartWidget(QWidget):
    """Matplotlib-based PDOS chart widget with styling matching HybridizationWindow."""
    system_requested = Signal(str)
    
    def __init__(self, orb_colors, parent=None):
        super().__init__(parent)
        self.orb_colors = orb_colors
        self._current_label = None
        self._current_cache = None
        self._is_dark_mode = False
        self._ef = 0.0
        self.axes_config = None
        self._integration_method = "trapezoid"
        self._current_range_name = "All"
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
        self.data_dlg = PDOSDataDialog(self)
        self.style_dlg = PDOSStyleDialog(self)
        self.axes_dlg = AxesConfigDialog(current_config=self.axes_config, parent=self)
        
        # Connect Apply buttons and real-time signals to redraw
        self.data_dlg.applied.connect(self._on_redraw_request)
        self.data_dlg.real_time_update.connect(self._on_redraw_request)
        self.data_dlg.system_changed.connect(self.system_requested.emit)
        self.style_dlg.applied.connect(self._on_redraw_request)
        self.style_dlg.real_time_update.connect(self._on_redraw_request)
        self.axes_dlg.applied.connect(self._on_axes_applied)
        self.axes_dlg.real_time_update.connect(self._on_axes_applied)
        
        # Style connects
        self.style_dlg.btn_color.clicked.connect(self._show_color_menu)
        self.style_dlg.combo_theme.currentIndexChanged.connect(self._on_theme_changed)
        
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
        
        # Wrap canvas in a horizontal layout to add margins on the left and right
        canvas_layout = QHBoxLayout()
        canvas_layout.setContentsMargins(50, 0, 50, 10)
        canvas_layout.addWidget(self.canvas)
        layout.addLayout(canvas_layout)
        
        self._axes = []
        
    def _on_axes_applied(self):
        self.axes_config = self.axes_dlg.get_config()
        self._on_redraw_request()
            
    def _show_color_menu(self):
        """Show a menu to pick which orbital to color."""
        menu = QMenu(self)
        for orb in d_orb_names:
            action = QAction(f"Color for {orb}", self)
            action.triggered.connect(lambda checked, o=orb: self._set_orb_color(o))
            menu.addAction(action)
        menu.exec_(self.style_dlg.btn_color.mapToGlobal(self.style_dlg.btn_color.rect().bottomLeft()))

    def _set_orb_color(self, orb):
        """Open color dialog to customize a specific orbital color."""
        current_hex = self.orb_colors.get(orb, "#000000")
        color = QColorDialog.getColor(QColor(current_hex), self, f"Pick Color for {orb}")
        if color.isValid():
            self.orb_colors[orb] = color.name()
            self._on_redraw_request()
        
    def _on_theme_changed(self):
        """Apply predefined color theme."""
        theme_name = self.style_dlg.combo_theme.currentText()
        colors = THEMES_CONFIG.get("5_color_dos", {}).get(theme_name)
        if colors and len(colors) >= 5:
            for i, orb in enumerate(d_orb_names):
                self.orb_colors[orb] = colors[i]
            self._on_redraw_request()
            
    def set_integration_method(self, method: str):
        """Set the numerical integration method for center annotation."""
        self._integration_method = method
        if self._current_label and self._current_cache:
            self._on_redraw_request()

    def set_current_range(self, range_name: str):
        """Set the integration range to use for d-band center annotations."""
        self._current_range_name = range_name

    def _parse_range_from_name(self):
        """Parse current range name into limit_fermi and custom_range."""
        name = getattr(self, '_current_range_name', 'All')
        if name == "< Ef":
            return True, None
        elif name.startswith("[") and name.endswith("]"):
            try:
                inner = name[1:-1]
                parts = inner.split(",")
                return False, (float(parts[0]), float(parts[1]))
            except Exception:
                pass
        return False, None

    def _on_redraw_request(self):
        """Redraw plot with current settings."""
        if self._current_label and self._current_cache:
            self.draw_pdos(self._current_label, self._current_cache)
            
    def clear_chart(self):
        """Clear the chart."""
        self._current_label = None
        self._current_cache = None
        self.fig.clear()
        self._axes = []
        self.canvas.draw()
        
    def update_systems(self, labels):
        """Update the list of systems in the data dialog."""
        self.data_dlg.update_systems(labels, self._current_label)

    def draw_pdos(self, label, cache_entry):
        """Draw PDOS plot with Matplotlib."""
        self._current_label = label
        self._current_cache = cache_entry
        self.data_dlg.set_current_system(label)
        
        e_raw = cache_entry["energy"]
        ef = cache_entry.get("ef", 0.0)
        self._ef = ef
        e = e_raw - ef
        
        rho_up = cache_entry["up"]
        rho_dn = cache_entry["down"]
        has_spin = cache_entry["has_spin"]
        
        mode = self.data_dlg.combo_plot_mode.currentText()
        if not has_spin:
            mode = "Total Only"
            
        # Clear figure
        self.fig.clear()
        self._axes = []
        
        # Determine subplot layout
        if mode == "All (3 Subplots)":
            gs = self.fig.add_gridspec(3, 1, height_ratios=[1, 1, 1])
            ax_tot = self.fig.add_subplot(gs[0, 0])
            ax_up = self.fig.add_subplot(gs[1, 0], sharex=ax_tot)
            ax_dn = self.fig.add_subplot(gs[2, 0], sharex=ax_tot)
            self._axes = [ax_tot, ax_up, ax_dn]
            
            self._draw_total(ax_tot, e, rho_up, rho_dn, True)
            ax_tot.set_title(f"{label} Total PDOS", fontsize=10, loc='left', pad=6)
            
            self._draw_spin(ax_up, e, rho_up, 1, "εd(up)", True)
            ax_up.set_title("Spin-Up d-DOS", fontsize=10, loc='left', pad=6)
            
            self._draw_spin(ax_dn, e, rho_dn, 1, "εd(dn)", True)
            ax_dn.set_title("Spin-Down d-DOS", fontsize=10, loc='left', pad=6)
            
            # Set common x-label
            ax_dn.set_xlabel("E − E$_{f}$ (eV)")
            
            # Set y-labels
            ax_tot.set_ylabel("DOS")
            ax_up.set_ylabel("DOS")
            ax_dn.set_ylabel("DOS")
            
        elif mode == "Total Only":
            ax = self.fig.add_subplot(111)
            self._axes = [ax]
            self._draw_total(ax, e, rho_up, rho_dn, True)
            ax.set_title(f"{label} Total PDOS", fontsize=10, loc='left', pad=6)
            ax.set_xlabel("E − E$_{f}$ (eV)")
            ax.set_ylabel("DOS")
            
        elif mode == "Spin-Up Only":
            ax = self.fig.add_subplot(111)
            self._axes = [ax]
            self._draw_spin(ax, e, rho_up, 1, "εd(up)", True)
            ax.set_title(f"{label} Spin-Up PDOS", fontsize=10, loc='left', pad=6)
            ax.set_xlabel("E − E$_{f}$ (eV)")
            ax.set_ylabel("DOS")
            
        elif mode == "Spin-Down Only":
            ax = self.fig.add_subplot(111)
            self._axes = [ax]
            self._draw_spin(ax, e, rho_dn, 1, "εd(dn)", True)
            ax.set_title(f"{label} Spin-Down PDOS", fontsize=10, loc='left', pad=6)
            ax.set_xlabel("E − E$_{f}$ (eV)")
            ax.set_ylabel("DOS")
            
        # Apply axes limits
        c = self.axes_config or {}
        x_min, x_max = c.get("x_min"), c.get("x_max")
        y_min, y_max = c.get("y_min"), c.get("y_max")
        
        for ax in self._axes:
            if x_min is not None and x_max is not None:
                ax.set_xlim(x_min, x_max)
            if y_min is not None and y_max is not None:
                ax.set_ylim(y_min, y_max)
                
        # Apply styling to all axes
        for ax in self._axes:
            self._apply_axes_style(ax)
            
        self._apply_dark_mode()
        self.canvas.draw()

    def set_dark_mode(self, is_dark):
        self._is_dark_mode = is_dark
        self._apply_dark_mode()

    def _apply_dark_mode(self):
        if not self.fig.axes:
            bg_color = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
            self.fig.patch.set_facecolor(bg_color)
            self.canvas.draw()
            return

        bg_color = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
        fg_color = "#E0E0E0" if self._is_dark_mode else "black"

        self.fig.patch.set_facecolor(bg_color)
        
        for ax in self._axes:
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
                # Keep center annotation color independent
                if getattr(text, '_original_color_set', False):
                    continue
                # Center annotation sets its own color, we will manually fix center color
                # but for now just check if color matches CENTER_COLOR
                if text.get_color() != CENTER_COLOR:
                    text.set_color(fg_color)
                
                # Check for bbox and update its background
                bbox = text.get_bbox_patch()
                if bbox is not None:
                    bbox.set_facecolor(bg_color)
                    bbox.set_edgecolor("none")

            leg = ax.get_legend()
            if leg:
                frame = leg.get_frame()
                frame.set_facecolor(bg_color)
                frame.set_edgecolor(fg_color)
                for text in leg.get_texts():
                    text.set_color(fg_color)
                    
        self.canvas.draw()
        
    def _apply_axes_style(self, ax):
        """Apply consistent axes styling matching hybridization plots."""
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
        
        # Set tick parameters strictly matching Matplotlib defaults (outward, clean bounding box)
        tdir = c.get("tick_dir", "out")
        ax.tick_params(axis='both', which='major', direction=tdir, labelsize=10, width=lw, length=5,
                       top=False, right=False)
        ax.tick_params(axis='both', which='minor', direction=tdir, width=max(0.4, lw*0.8), length=3,
                       top=False, right=False)
                       
        # Set legend
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            # frameon=False removes the bounding box completely
            ax.legend(fontsize=8, ncol=5, loc='upper right', frameon=False, columnspacing=1.0, handletextpad=0.4)
            
    def _draw_total(self, ax, e, rho_up, rho_dn, show_legend):
        """Draw total PDOS (sum of all d-orbitals)."""
        self._plot_orbital_lines(ax, e, rho_up, spin_sign=1, show_legend=show_legend)
        
        if rho_dn:
            self._plot_orbital_lines(ax, e, rho_dn, spin_sign=-1, show_legend=False)
            
        if self.data_dlg.chk_show_center.isChecked():
            rho_tot = {}
            for o in d_orb_names:
                u = rho_up.get(o, np.zeros_like(e))
                d = rho_dn.get(o, np.zeros_like(e)) if rho_dn else np.zeros_like(e)
                rho_tot[o] = u + d
            self._draw_center_annotation(ax, e, rho_tot, "εd(tot)")
            
    def _draw_spin(self, ax, e, rho_dict, sign, tag, show_legend):
        """Draw spin-resolved PDOS."""
        self._plot_orbital_lines(ax, e, rho_dict, spin_sign=sign, show_legend=show_legend)
        
        if self.data_dlg.chk_show_center.isChecked() and rho_dict is not None:
            self._draw_center_annotation(ax, e, rho_dict, tag)
            
    def _plot_orbital_lines(self, ax, e, rho_dict, spin_sign, show_legend):
        """Plot orbital lines with fill."""
        lw = self.style_dlg.spin_lw.value()
        do_fill = self.style_dlg.chk_fill.isChecked()
        alpha = self.style_dlg.spin_alpha.value()
        
        for o in d_orb_names:
            dos = rho_dict.get(o, np.zeros_like(e)) * spin_sign
            hex_color = self.orb_colors.get(o, "#000000")
            
            # Plot line
            ax.plot(e, dos, color=hex_color, lw=lw, label=format_orbital_display(o) if show_legend else None)
            
            # Fill if requested
            if do_fill:
                ax.fill_between(e, 0, dos, color=hex_color, alpha=alpha, zorder=1)
                
    def _draw_center_annotation(self, ax, e, rho_dict, tag):
        """Draw vertical line and annotation for d-band center."""
        limit_fermi, custom_range = self._parse_range_from_name()
        
        center, _, _, _ = calc_metrics(e, rho_dict, ef=0.0,
                                        orb_names=d_orb_names,
                                        limit_fermi=limit_fermi,
                                        custom_range=custom_range,
                                        method=self._integration_method)
        
        range_str = getattr(self, '_current_range_name', 'All')
        if range_str.startswith("["):
            range_str = "Custom"
            
        c = self.axes_config or {}
        x_min = c.get("x_min")
        x_max = c.get("x_max")
        
        if x_min is None or x_max is None:
            curr_x_min, curr_x_max = ax.get_xlim()
            x_min = x_min if x_min is not None else curr_x_min
            x_max = x_max if x_max is not None else curr_x_max

        text_str = f"{tag}={center:.4f} eV ({range_str})"
        if x_min <= center <= x_max:
            # Inside visible area: draw line and text at the center
            ax.axvline(center, color=CENTER_COLOR, lw=CENTER_LW, ls='--', zorder=3)
            transform = ax.get_xaxis_transform()
            x_offset = (x_max - x_min) * 0.002
            ax.text(center + x_offset, 0.9, text_str, 
                    color=CENTER_COLOR, fontsize=CENTER_FONTSIZE,
                    verticalalignment='top', horizontalalignment='left', zorder=4,
                    transform=transform, clip_on=True)
        else:
            # Outside visible area: draw text in the top-left corner
            ax.text(0.01, 0.9, text_str, 
                    color=CENTER_COLOR, fontsize=CENTER_FONTSIZE,
                    verticalalignment='top', horizontalalignment='left', zorder=4,
                    transform=ax.transAxes, clip_on=False)
        
    def get_figure(self):
        """Return the matplotlib figure for export."""
        return self.fig
