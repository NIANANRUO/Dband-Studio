import traceback

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton
)
from PySide6.QtCore import Qt, QTimer
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from utils.styling import BAR_COLORS
from ui.charts.bar_chart_dialogs import (
    BarChartDataDialog, BarChartPatternDialog, BarChartLabelsDialog,
    BarChartAxesDialog, BarChartLegendDialog
)


class BarChartWidget(QWidget):
    """Bar chart comparing d-band centers across files and ranges with Origin-like controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_data = None
        self._is_dark_mode = False
        self._is_building = True
        self._prev_n_labels = 0
        self._prev_n_ranges = 0
        self._rendered_labels = []
        self._build_ui()
        # Debounce timer: coalesce rapid control changes into a single redraw
        # to prevent event-loop starvation when dragging sliders.
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(80)  # ms
        self._debounce_timer.timeout.connect(self._do_delayed_update)
        self._is_building = False

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Instantiate floating dialogs
        self.data_dlg = BarChartDataDialog(self)
        self.pattern_dlg = BarChartPatternDialog(self)
        self.labels_dlg = BarChartLabelsDialog(self)
        self.axes_dlg = BarChartAxesDialog(self)
        self.legend_dlg = BarChartLegendDialog(self)
        
        self.data_dlg.real_time_update.connect(self._trigger_update)
        self.pattern_dlg.applied.connect(self._trigger_update)
        self.pattern_dlg.real_time_update.connect(self._trigger_update)
        self.labels_dlg.applied.connect(self._trigger_update)
        self.labels_dlg.real_time_update.connect(self._trigger_update)
        self.axes_dlg.applied.connect(self._trigger_update)
        self.axes_dlg.real_time_update.connect(self._trigger_update)
        self.legend_dlg.applied.connect(self._trigger_update)
        self.legend_dlg.real_time_update.connect(self._trigger_update)
        
        # We replace the TabBar with a simple Widget containing tool buttons
        # This will be embedded in MainWindow's corner.
        self.toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(self.toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(4)

        btn_data = QPushButton("📊 Data")
        btn_data.clicked.connect(self.data_dlg.show)
        toolbar_layout.addWidget(btn_data)
        
        btn_pattern = QPushButton("🎨 Pattern")
        btn_pattern.clicked.connect(self.pattern_dlg.show)
        toolbar_layout.addWidget(btn_pattern)
        
        btn_labels = QPushButton("🏷️ Labels")
        btn_labels.clicked.connect(self.labels_dlg.show)
        toolbar_layout.addWidget(btn_labels)
        
        btn_axes = QPushButton("⚙️ Axes")
        btn_axes.clicked.connect(self.axes_dlg.show)
        toolbar_layout.addWidget(btn_axes)
        
        btn_legend = QPushButton("🗂️ Legend")
        btn_legend.clicked.connect(self.legend_dlg.show)
        toolbar_layout.addWidget(btn_legend)

        # Canvas
        self.fig = Figure(constrained_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.hide()  # Hidden, used for programmatic zoom/home
        self.toolbar.zoom()  # Enable zoom-to-rect by default

        canvas_layout = QHBoxLayout()
        canvas_layout.setContentsMargins(50, 0, 50, 10)
        canvas_layout.addWidget(self.canvas)
        layout.addLayout(canvas_layout)

    # ------------------------------------------------------------------ #
    #  Update trigger — debounced + exception-guarded
    # ------------------------------------------------------------------ #

    def _trigger_update(self, *args):
        """Called by any control signal; coalesce into one redraw via debounce timer."""
        if not self._is_building and self._current_data is not None:
            self._debounce_timer.start()

    def _do_delayed_update(self):
        """Actual redraw after debounce interval; exceptions are caught and logged."""
        if self._current_data is None or self._is_building:
            return
        try:
            self.update_chart(self._current_data)
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------ #
    #  Control-tab builders
    # ------------------------------------------------------------------ #



    # ------------------------------------------------------------------ #
    #  Auto-label adjustment
    # ------------------------------------------------------------------ #

    def _auto_set_labels_based_on_data(self, n_labels, n_ranges):
        """Auto-adjust label settings based on data volume to avoid overlap.

        Guarded by ``_is_building`` to prevent the valueChanged signals
        fired after ``blockSignals(False)`` from triggering a recursive
        ``update_chart`` call.
        """
        self._is_building = True

        if n_labels <= 5 and n_ranges <= 3:
            self.labels_dlg.spin_xtick_fs.setValue(9)
            self.labels_dlg.spin_xtick_rot.setValue(0)
            self.labels_dlg.spin_val_fs.setValue(8)
            self.labels_dlg.chk_show_labels.setChecked(True)
        elif n_labels <= 10 and n_ranges <= 5:
            self.labels_dlg.spin_xtick_fs.setValue(8)
            self.labels_dlg.spin_xtick_rot.setValue(45)
            self.labels_dlg.spin_val_fs.setValue(7)
            self.labels_dlg.chk_show_labels.setChecked(True)
        else:
            self.labels_dlg.spin_xtick_fs.setValue(7)
            self.labels_dlg.spin_xtick_rot.setValue(60)
            self.labels_dlg.spin_val_fs.setValue(6)
            self.labels_dlg.chk_show_labels.setChecked(False)

        self._is_building = False

    # ------------------------------------------------------------------ #
    #  Main chart rendering
    # ------------------------------------------------------------------ #

    def _sync_system_selector(self, results_data):
        """Refresh available labels without discarding valid user selections."""
        labels = list(dict.fromkeys(d.label for d in results_data))
        combo = self.data_dlg.combo_systems
        had_items = combo.count() > 0
        previous_checked = set(combo.get_checked_items())
        previous_labels = {combo.itemText(i) for i in range(combo.count())}

        combo.blockSignals(True)
        combo.clear_items()
        for label in labels:
            checked = True if not had_items or label not in previous_labels else label in previous_checked
            combo.add_item(label, checked=checked)
        combo.blockSignals(False)

    def update_chart(self, results_data):
        """Rebuild the bar chart from *results_data*.

        Called either externally (after calculation / workspace load) or
        internally via the debounced ``_do_delayed_update``.
        """
        # Detect first load OR significant data-shape change so that
        # label auto-adjustment fires when the number of bars changes
        # substantially, not only on the very first render.
        is_first_load = (self._current_data is None and results_data is not None)
        self._current_data = list(results_data or [])
        self._sync_system_selector(self._current_data)

        selected_labels = set(self.data_dlg.combo_systems.get_checked_items())
        render_data = [d for d in self._current_data if d.label in selected_labels]
        self._rendered_labels = list(dict.fromkeys(d.label for d in render_data))

        self.fig.clear()
        if not render_data:
            self.canvas.draw()
            return

        labels = self._rendered_labels
        ranges = list(dict.fromkeys(d.range_name for d in render_data))

        render_n_labels = len(labels)
        render_n_ranges = len(ranges)
        auto_n_labels = len(dict.fromkeys(d.label for d in self._current_data))
        auto_n_ranges = len(dict.fromkeys(d.range_name for d in self._current_data))
        data_changed = (
            auto_n_labels != self._prev_n_labels or
            auto_n_ranges != self._prev_n_ranges
        )
        if is_first_load or data_changed:
            self._auto_set_labels_based_on_data(auto_n_labels, auto_n_ranges)
        self._prev_n_labels = auto_n_labels
        self._prev_n_ranges = auto_n_ranges

        # --- Read UI States ---
        # Pattern
        theme_name = self.pattern_dlg.combo_theme.currentText()
        colors = self.pattern_dlg.theme_dict.get(theme_name, BAR_COLORS)
        if not colors:
            colors = BAR_COLORS
        b_width = self.pattern_dlg.spin_bar_width.value()
        bar_gap_pct = self.pattern_dlg.spin_bar_gap.value() / 100.0
        edge_c_mode = self.pattern_dlg.combo_edge_color.currentText()
        edge_w = self.pattern_dlg.spin_edge_width.value()
        alpha = self.pattern_dlg.slider_alpha.value() / 100.0

        # Labels
        show_val = self.labels_dlg.chk_show_labels.isChecked()
        val_fs = self.labels_dlg.spin_val_fs.value()
        xtick_fs = self.labels_dlg.spin_xtick_fs.value()
        xtick_rot = self.labels_dlg.spin_xtick_rot.value()
        val_pos = self.labels_dlg.combo_label_pos.currentText()

        # Axes — 4 independent tick visibilities
        spine_w = self.axes_dlg.spin_spine_width.value()
        x_tick_dir = self.axes_dlg.combo_tick_dir_x.currentText()
        y_tick_dir = self.axes_dlg.combo_tick_dir_y.currentText()
        bottom_ticks = self.axes_dlg.chk_bottom_ticks.isChecked()
        top_ticks = self.axes_dlg.chk_top_ticks.isChecked()
        left_ticks = self.axes_dlg.chk_left_ticks.isChecked()
        right_ticks = self.axes_dlg.chk_right_ticks.isChecked()
        show_grid = self.axes_dlg.chk_grid.isChecked()
        show_zero = self.axes_dlg.chk_zero_line.isChecked()

        # Legend
        show_leg = self.legend_dlg.chk_show_legend.isChecked()
        leg_fs = self.legend_dlg.spin_leg_fs.value()
        leg_scale = self.legend_dlg.spin_leg_scale.value()
        leg_pos = self.legend_dlg.combo_leg_pos.currentText()
        leg_cols = self.legend_dlg.spin_leg_cols.value()
        leg_frame = self.legend_dlg.chk_leg_frame.isChecked()

        # --- Drawing ---
        ax = self.fig.add_subplot(111)

        x = np.arange(render_n_labels)
        
        if render_n_ranges:
            # We want total group width to be b_width.
            # There are n_ranges bars and (n_ranges - 1) gaps.
            # Total width = n_ranges * w + (n_ranges - 1) * w * bar_gap_pct
            # w = b_width / (n_ranges + (n_ranges - 1) * bar_gap_pct)
            w = b_width / (render_n_ranges + (render_n_ranges - 1) * bar_gap_pct)
        else:
            w = 0.5

        # Pre-compute label offset from data range so labels don't touch bars
        _all_centers = [d.center for d in render_data if np.isfinite(d.center)]
        _y_range = max(_all_centers) - min(_all_centers) if len(_all_centers) > 1 else 4.0
        _y_range = max(_y_range, 1e-6)
        _label_pad = _y_range * 0.04  # 4% of Y range as visual gap

        for i, rn in enumerate(ranges):
            centers = []
            for lb in labels:
                v = next(
                    (d.center for d in render_data
                     if d.label == lb and d.range_name == rn),
                    np.nan,
                )
                centers.append(v)
            # Center the group: start at -b_width / 2 + w / 2, add step size (w + w * bar_gap_pct)
            off = -b_width / 2.0 + w / 2.0 + i * w * (1.0 + bar_gap_pct)

            fill_c = colors[i % len(colors)]
            if edge_c_mode == "White":
                e_c = "white"
            elif edge_c_mode == "Black":
                e_c = "black"
            elif edge_c_mode == "None":
                e_c = "none"
            else:
                e_c = fill_c  # Same as Fill

            bars = ax.bar(
                x + off, centers, w, label=rn,
                color=fill_c, alpha=alpha,
                edgecolor=e_c, linewidth=edge_w,
            )

            if show_val:
                for bar, val in zip(bars, centers):
                    if np.isfinite(val):
                        # Default: outside (above positive / below negative)
                        va = "bottom" if val >= 0 else "top"
                        y_pos = bar.get_height()

                        if val_pos == "Center":
                            va = "center"
                            y_pos = y_pos / 2.0
                        elif val_pos == "Inside Base":
                            va = "bottom" if val >= 0 else "top"
                            y_pos = 0.01 if val >= 0 else -0.01
                        elif val_pos == "Auto (Outside)":
                            # Add padding so label doesn't touch the bar edge
                            if val >= 0:
                                y_pos += _label_pad   # push text upward
                            else:
                                y_pos -= _label_pad   # push text downward

                        ax.text(
                            bar.get_x() + bar.get_width() / 2, y_pos,
                            f"{val:.3f}",
                            ha="center", va=va, fontsize=val_fs,
                            color="black", weight="bold",
                        )

        ax.set_ylabel("d-band Center (eV)", fontsize=10, weight="bold")
        ax.set_title("d-band Center Comparison", fontsize=11, weight="bold")
        ax.set_xticks(x)
        if xtick_rot == 0:
            ax.set_xticklabels(labels, rotation=xtick_rot, ha="center",
                               fontsize=xtick_fs)
        else:
            ax.set_xticklabels(labels, rotation=xtick_rot, ha="right",
                               rotation_mode="anchor", fontsize=xtick_fs)

        # --- Apply Axes formatting ---
        for spine in ax.spines.values():
            spine.set_linewidth(spine_w)
            spine.set_visible(True)  # all four spines always visible

        if show_grid:
            grid_color = "#555555" if getattr(self, '_is_dark_mode', False) else "#E0E0E0"
            ax.grid(True, linestyle=":", alpha=0.6, color=grid_color, zorder=0)
        else:
            ax.grid(False)

        # Tick formatting — 4-way independent control via tick_params
        ax.tick_params(
            axis='x',
            direction=x_tick_dir, width=spine_w,
            bottom=bottom_ticks, top=top_ticks,
            labelbottom=True,
        )
        ax.tick_params(
            axis='y',
            direction=y_tick_dir, width=spine_w,
            left=left_ticks, right=right_ticks,
            labelleft=True,
        )

        if show_grid:
            ax.grid(axis='y', linestyle='--', alpha=0.3, zorder=0)

        if show_zero:
            ax.axhline(0, color="black", ls="--", lw=spine_w)

        # Padding for outside labels to prevent clipping
        if show_val and val_pos == "Auto (Outside)":
            ymin, ymax = ax.get_ylim()
            y_range = ymax - ymin
            ax.set_ylim(ymin - 0.1 * y_range, ymax + 0.1 * y_range)

        # --- Apply Legend formatting ---
        if show_leg:
            bbox = None
            loc = leg_pos
            if leg_pos == "outside top":
                loc = "lower center"
                bbox = (0.5, 1.05)
            elif leg_pos == "outside right":
                loc = "center left"
                bbox = (1.02, 0.5)

            leg = ax.legend(
                fontsize=leg_fs, loc=loc, bbox_to_anchor=bbox,
                ncol=leg_cols, frameon=leg_frame, markerscale=leg_scale,
            )
            # Apply scale to legend handle linewidths.
            # Use getattr for cross-version matplotlib compatibility.
            legend_handles = (
                getattr(leg, "legend_handles", None)
                or getattr(leg, "legendHandles", None)
                or []
            )
            for legobj in legend_handles:
                if hasattr(legobj, "set_linewidth"):
                    legobj.set_linewidth(edge_w * leg_scale)

        self._apply_dark_mode()
        self.canvas.draw()

    def set_dark_mode(self, is_dark):
        self._is_dark_mode = is_dark
        self._apply_dark_mode()

    def _apply_dark_mode(self):
        if not self.fig.axes:
            # If chart is clear, just set figure background
            bg_color = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
            self.fig.patch.set_facecolor(bg_color)
            self.canvas.draw()
            return
            
        ax = self.fig.axes[0]
        bg_color = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
        fg_color = "#E0E0E0" if self._is_dark_mode else "black"

        self.fig.patch.set_facecolor(bg_color)
        ax.set_facecolor(bg_color)
        
        ax.tick_params(colors=fg_color, which='both')
        for spine in ax.spines.values():
            spine.set_color(fg_color)
            
        ax.xaxis.label.set_color(fg_color)
        ax.yaxis.label.set_color(fg_color)
        ax.title.set_color(fg_color)
        
        for text in ax.texts:
            text.set_color(fg_color)

        leg = ax.get_legend()
        if leg:
            frame = leg.get_frame()
            frame.set_facecolor(bg_color)
            frame.set_edgecolor(fg_color)
            for text in leg.get_texts():
                text.set_color(fg_color)
                    
        self.canvas.draw()

    def clear_chart(self):
        self._debounce_timer.stop()
        self._current_data = None
        self._prev_n_labels = 0
        self._prev_n_ranges = 0
        self.fig.clear()
        self.canvas.draw()
