from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QDoubleSpinBox, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt, Signal
from ui.widgets.floating_dialog_base import FloatingConfigDialog

class AxesConfigDialog(FloatingConfigDialog):
    """Dialog for advanced matplotlib axes configuration."""
    real_time_update = Signal()
    
    def __init__(self, current_config=None, parent=None):
        super().__init__(title="Axes Settings", parent=parent)
        self.setMinimumWidth(350)
        
        # Default config
        self.config = {
            "x_min": None, "x_max": None,
            "y_min": None, "y_max": None,
            "spine_lw": 1.0,
            "spine_top": True,
            "spine_right": True,
            "spine_bottom": True,
            "spine_bottom": True,
            "spine_left": True,
            "tick_dir": "out",
            "show_grid": False
        }
        if current_config:
            self.config.update(current_config)
            
        self._build_ui()
        self._load_config()
        
    def _build_ui(self):
        # Use content_layout from FloatingConfigDialog
        layout = self.content_layout
        layout.setSpacing(15)
        
        # 1. Range Configuration
        group_range = QGroupBox("Coordinate Ranges")
        grid_range = QGridLayout(group_range)
        
        grid_range.addWidget(QLabel("X Range:"), 0, 0)
        self.entry_x_min = QLineEdit()
        self.entry_x_min.setPlaceholderText("Min")
        self.entry_x_min.textChanged.connect(lambda *args: self.real_time_update.emit())
        grid_range.addWidget(self.entry_x_min, 0, 1)
        grid_range.addWidget(QLabel("to"), 0, 2)
        self.entry_x_max = QLineEdit()
        self.entry_x_max.setPlaceholderText("Max")
        self.entry_x_max.textChanged.connect(lambda *args: self.real_time_update.emit())
        grid_range.addWidget(self.entry_x_max, 0, 3)
        
        grid_range.addWidget(QLabel("Y Range:"), 1, 0)
        self.entry_y_min = QLineEdit()
        self.entry_y_min.setPlaceholderText("Min")
        self.entry_y_min.textChanged.connect(lambda *args: self.real_time_update.emit())
        grid_range.addWidget(self.entry_y_min, 1, 1)
        grid_range.addWidget(QLabel("to"), 1, 2)
        self.entry_y_max = QLineEdit()
        self.entry_y_max.setPlaceholderText("Max")
        self.entry_y_max.textChanged.connect(lambda *args: self.real_time_update.emit())
        grid_range.addWidget(self.entry_y_max, 1, 3)
        
        layout.addWidget(group_range)
        
        # 2. Spines Configuration
        group_spines = QGroupBox("Spines (Borders)")
        vbox_spines = QVBoxLayout(group_spines)
        
        row_lw = QHBoxLayout()
        row_lw.addWidget(QLabel("Line Width:"))
        self.spin_spine_lw = QDoubleSpinBox()
        self.spin_spine_lw.setRange(0.1, 5.0)
        self.spin_spine_lw.setSingleStep(0.1)
        self.spin_spine_lw.valueChanged.connect(lambda *args: self.real_time_update.emit())
        row_lw.addWidget(self.spin_spine_lw)
        row_lw.addStretch()
        vbox_spines.addLayout(row_lw)
        
        row_vis = QHBoxLayout()
        row_vis.addWidget(QLabel("Show:"))
        self.chk_top = QCheckBox("Top")
        self.chk_right = QCheckBox("Right")
        self.chk_bottom = QCheckBox("Bottom")
        self.chk_left = QCheckBox("Left")
        for chk in (self.chk_top, self.chk_right, self.chk_bottom, self.chk_left):
            chk.stateChanged.connect(lambda *args: self.real_time_update.emit())
            row_vis.addWidget(chk)
        vbox_spines.addLayout(row_vis)
        
        layout.addWidget(group_spines)
        
        # 3. Ticks Configuration
        group_ticks = QGroupBox("Ticks")
        row_ticks = QHBoxLayout(group_ticks)
        
        row_ticks.addWidget(QLabel("Tick Direction:"))
        self.combo_tick_dir = QComboBox()
        self.combo_tick_dir.addItems(["out", "in", "inout"])
        self.combo_tick_dir.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        row_ticks.addWidget(self.combo_tick_dir)
        
        self.chk_grid = QCheckBox("Show Grid")
        self.chk_grid.stateChanged.connect(lambda *args: self.real_time_update.emit())
        row_ticks.addWidget(self.chk_grid)
        row_ticks.addStretch()
        
        layout.addWidget(group_ticks)
        
        layout.addWidget(group_ticks)

        
    def _load_config(self):
        c = self.config
        
        def set_val(entry, val):
            entry.setText(str(val) if val is not None else "")
            
        set_val(self.entry_x_min, c["x_min"])
        set_val(self.entry_x_max, c["x_max"])
        set_val(self.entry_y_min, c["y_min"])
        set_val(self.entry_y_max, c["y_max"])
        
        self.spin_spine_lw.setValue(c["spine_lw"])
        self.chk_top.setChecked(c["spine_top"])
        self.chk_right.setChecked(c["spine_right"])
        self.chk_bottom.setChecked(c["spine_bottom"])
        self.chk_left.setChecked(c["spine_left"])
        
        idx = self.combo_tick_dir.findText(c["tick_dir"])
        if idx >= 0:
            self.combo_tick_dir.setCurrentIndex(idx)
            
        self.chk_grid.setChecked(c.get("show_grid", False))
            
    def get_config(self):
        def get_val(entry):
            t = entry.text().strip()
            if not t:
                return None
            try:
                return float(t)
            except ValueError:
                return None
                
        return {
            "x_min": get_val(self.entry_x_min),
            "x_max": get_val(self.entry_x_max),
            "y_min": get_val(self.entry_y_min),
            "y_max": get_val(self.entry_y_max),
            "spine_lw": self.spin_spine_lw.value(),
            "spine_top": self.chk_top.isChecked(),
            "spine_right": self.chk_right.isChecked(),
            "spine_bottom": self.chk_bottom.isChecked(),
            "spine_bottom": self.chk_bottom.isChecked(),
            "spine_left": self.chk_left.isChecked(),
            "tick_dir": self.combo_tick_dir.currentText(),
            "show_grid": self.chk_grid.isChecked()
        }
