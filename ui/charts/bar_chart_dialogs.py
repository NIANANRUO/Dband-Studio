from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QCheckBox, QSpinBox, QDoubleSpinBox, QSlider, QWidget
)
from PySide6.QtCore import Qt, Signal
from ui.widgets.floating_dialog_base import FloatingConfigDialog
from ui.widgets.checkable_combo import CheckableComboBox
from utils.styling import THEMES_CONFIG


class BarChartDataDialog(FloatingConfigDialog):
    """Select which calculated systems are visible in the comparison chart."""

    real_time_update = Signal()

    def __init__(self, parent=None):
        super().__init__(title="Data Control", parent=parent)
        layout = self.content_layout
        row = QHBoxLayout()
        row.addWidget(QLabel("Systems:"))
        self.combo_systems = CheckableComboBox()
        self.combo_systems.setMinimumWidth(150)
        self.combo_systems.selection_changed.connect(self.real_time_update.emit)
        row.addWidget(self.combo_systems)
        layout.addLayout(row)

class BarChartPatternDialog(FloatingConfigDialog):
    real_time_update = Signal()

    def __init__(self, parent=None):
        super().__init__(title="Graph Pattern", parent=parent)
        self._build_ui()

    def _build_ui(self):
        layout = self.content_layout
        
        # Theme
        hbox1 = QHBoxLayout()
        hbox1.addWidget(QLabel("Theme:"))
        self.combo_theme = QComboBox()
        self.theme_dict = {}
        for cat in ["3_color", "4_color", "multi_color"]:
            self.theme_dict.update(THEMES_CONFIG.get(cat, {}))
        self.combo_theme.addItems(list(self.theme_dict.keys()))
        hbox1.addWidget(self.combo_theme)
        layout.addLayout(hbox1)

        # Group Width
        hbox2 = QHBoxLayout()
        hbox2.addWidget(QLabel("Group Width:"))
        self.spin_bar_width = QDoubleSpinBox()
        self.spin_bar_width.setRange(0.1, 1.0)
        self.spin_bar_width.setSingleStep(0.1)
        self.spin_bar_width.setValue(0.7)
        self.spin_bar_width.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox2.addWidget(self.spin_bar_width)
        layout.addLayout(hbox2)

        # Intra-group Bar Gap
        hbox_gap = QHBoxLayout()
        hbox_gap.addWidget(QLabel("Bar Gap (%):"))
        self.spin_bar_gap = QDoubleSpinBox()
        self.spin_bar_gap.setRange(-50.0, 100.0)
        self.spin_bar_gap.setSingleStep(5.0)
        self.spin_bar_gap.setValue(0.0)
        self.spin_bar_gap.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox_gap.addWidget(self.spin_bar_gap)
        layout.addLayout(hbox_gap)

        # Edge Color
        hbox3 = QHBoxLayout()
        hbox3.addWidget(QLabel("Edge Color:"))
        self.combo_edge_color = QComboBox()
        self.combo_edge_color.addItems(["Black", "White", "None", "Same as Fill"])
        self.combo_edge_color.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        hbox3.addWidget(self.combo_edge_color)
        layout.addLayout(hbox3)

        # Edge Width
        hbox4 = QHBoxLayout()
        hbox4.addWidget(QLabel("Edge Width:"))
        self.spin_edge_width = QDoubleSpinBox()
        self.spin_edge_width.setRange(0.0, 5.0)
        self.spin_edge_width.setSingleStep(0.5)
        self.spin_edge_width.setValue(1.0)
        self.spin_edge_width.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox4.addWidget(self.spin_edge_width)
        layout.addLayout(hbox4)

        # Alpha
        hbox5 = QHBoxLayout()
        hbox5.addWidget(QLabel("Alpha:"))
        self.slider_alpha = QSlider(Qt.Horizontal)
        self.slider_alpha.setRange(10, 100)
        self.slider_alpha.setValue(100)
        self.slider_alpha.setFixedWidth(100)
        self.slider_alpha.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox5.addWidget(self.slider_alpha)
        layout.addLayout(hbox5)


class BarChartLabelsDialog(FloatingConfigDialog):
    real_time_update = Signal()

    def __init__(self, parent=None):
        super().__init__(title="Labels", parent=parent)
        self._build_ui()

    def _build_ui(self):
        layout = self.content_layout
        
        self.chk_show_labels = QCheckBox("Show Value Labels")
        self.chk_show_labels.setChecked(True)
        self.chk_show_labels.stateChanged.connect(lambda *args: self.real_time_update.emit())
        layout.addWidget(self.chk_show_labels)

        hbox1 = QHBoxLayout()
        hbox1.addWidget(QLabel("Position:"))
        self.combo_label_pos = QComboBox()
        self.combo_label_pos.addItems(["Auto (Outside)", "Center", "Inside Base"])
        self.combo_label_pos.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        hbox1.addWidget(self.combo_label_pos)
        layout.addLayout(hbox1)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(QLabel("Value Font Size:"))
        self.spin_val_fs = QSpinBox()
        self.spin_val_fs.setRange(4, 24)
        self.spin_val_fs.setValue(8)
        self.spin_val_fs.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox2.addWidget(self.spin_val_fs)
        layout.addLayout(hbox2)

        hbox3 = QHBoxLayout()
        hbox3.addWidget(QLabel("X-Tick Font Size:"))
        self.spin_xtick_fs = QSpinBox()
        self.spin_xtick_fs.setRange(4, 24)
        self.spin_xtick_fs.setValue(9)
        self.spin_xtick_fs.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox3.addWidget(self.spin_xtick_fs)
        layout.addLayout(hbox3)

        hbox4 = QHBoxLayout()
        hbox4.addWidget(QLabel("X-Tick Rotation:"))
        self.spin_xtick_rot = QSpinBox()
        self.spin_xtick_rot.setRange(0, 90)
        self.spin_xtick_rot.setValue(0)
        self.spin_xtick_rot.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox4.addWidget(self.spin_xtick_rot)
        layout.addLayout(hbox4)


class BarChartAxesDialog(FloatingConfigDialog):
    real_time_update = Signal()

    def __init__(self, parent=None):
        super().__init__(title="Axes & Ticks", parent=parent)
        self._build_ui()

    def _build_ui(self):
        layout = self.content_layout

        hbox1 = QHBoxLayout()
        hbox1.addWidget(QLabel("Spine Width:"))
        self.spin_spine_width = QDoubleSpinBox()
        self.spin_spine_width.setRange(0.1, 3.0)
        self.spin_spine_width.setSingleStep(0.1)
        self.spin_spine_width.setValue(1.2)
        self.spin_spine_width.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox1.addWidget(self.spin_spine_width)
        layout.addLayout(hbox1)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(QLabel("Tick Dir X/Y:"))
        self.combo_tick_dir_x = QComboBox()
        self.combo_tick_dir_x.addItems(["out", "in"])
        self.combo_tick_dir_x.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        self.combo_tick_dir_y = QComboBox()
        self.combo_tick_dir_y.addItems(["out", "in"])
        self.combo_tick_dir_y.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        hbox2.addWidget(self.combo_tick_dir_x)
        hbox2.addWidget(self.combo_tick_dir_y)
        layout.addLayout(hbox2)

        hbox3 = QHBoxLayout()
        hbox3.addWidget(QLabel("Ticks:"))
        self.chk_bottom_ticks = QCheckBox("Bot")
        self.chk_bottom_ticks.setChecked(True)
        self.chk_left_ticks = QCheckBox("Lft")
        self.chk_left_ticks.setChecked(True)
        self.chk_top_ticks = QCheckBox("Top")
        self.chk_right_ticks = QCheckBox("Rgt")
        for chk in [self.chk_bottom_ticks, self.chk_left_ticks, self.chk_top_ticks, self.chk_right_ticks]:
            chk.stateChanged.connect(lambda *args: self.real_time_update.emit())
            hbox3.addWidget(chk)
        layout.addLayout(hbox3)

        self.chk_grid = QCheckBox("Grid")
        self.chk_grid.stateChanged.connect(lambda *args: self.real_time_update.emit())
        self.chk_zero_line = QCheckBox("Y=0 Line")
        self.chk_zero_line.setChecked(True)
        self.chk_zero_line.stateChanged.connect(lambda *args: self.real_time_update.emit())
        layout.addWidget(self.chk_grid)
        layout.addWidget(self.chk_zero_line)


class BarChartLegendDialog(FloatingConfigDialog):
    real_time_update = Signal()

    def __init__(self, parent=None):
        super().__init__(title="Legend", parent=parent)
        self._build_ui()

    def _build_ui(self):
        layout = self.content_layout

        self.chk_show_legend = QCheckBox("Show Legend")
        self.chk_show_legend.setChecked(True)
        self.chk_show_legend.stateChanged.connect(lambda *args: self.real_time_update.emit())
        layout.addWidget(self.chk_show_legend)

        hbox1 = QHBoxLayout()
        hbox1.addWidget(QLabel("Font Size:"))
        self.spin_leg_fs = QSpinBox()
        self.spin_leg_fs.setRange(4, 24)
        self.spin_leg_fs.setValue(9)
        self.spin_leg_fs.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox1.addWidget(self.spin_leg_fs)
        layout.addLayout(hbox1)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(QLabel("Marker Scale:"))
        self.spin_leg_scale = QDoubleSpinBox()
        self.spin_leg_scale.setRange(0.1, 3.0)
        self.spin_leg_scale.setSingleStep(0.1)
        self.spin_leg_scale.setValue(1.0)
        self.spin_leg_scale.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox2.addWidget(self.spin_leg_scale)
        layout.addLayout(hbox2)

        hbox3 = QHBoxLayout()
        hbox3.addWidget(QLabel("Position:"))
        self.combo_leg_pos = QComboBox()
        self.combo_leg_pos.addItems([
            "best", "upper right", "upper left",
            "lower right", "lower left", "outside top", "outside right"
        ])
        self.combo_leg_pos.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        hbox3.addWidget(self.combo_leg_pos)
        layout.addLayout(hbox3)

        hbox4 = QHBoxLayout()
        hbox4.addWidget(QLabel("Columns:"))
        self.spin_leg_cols = QSpinBox()
        self.spin_leg_cols.setRange(1, 10)
        self.spin_leg_cols.setValue(1)
        self.spin_leg_cols.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox4.addWidget(self.spin_leg_cols)
        layout.addLayout(hbox4)

        self.chk_leg_frame = QCheckBox("Frame")
        self.chk_leg_frame.stateChanged.connect(lambda *args: self.real_time_update.emit())
        layout.addWidget(self.chk_leg_frame)
