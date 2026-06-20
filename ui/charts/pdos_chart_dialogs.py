from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QCheckBox, QSpinBox, QDoubleSpinBox, QPushButton
)
from PySide6.QtCore import Qt, Signal
from ui.widgets.floating_dialog_base import FloatingConfigDialog
from utils.styling import THEMES_CONFIG

class PDOSDataDialog(FloatingConfigDialog):
    real_time_update = Signal()
    system_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(title="Data Control", parent=parent)
        self._build_ui()

    def _build_ui(self):
        layout = self.content_layout

        hbox_sys = QHBoxLayout()
        hbox_sys.addWidget(QLabel("System:"))
        self.combo_system = QComboBox()
        self.combo_system.activated.connect(self._on_system_activated)
        hbox_sys.addWidget(self.combo_system)
        layout.addLayout(hbox_sys)

        hbox1 = QHBoxLayout()
        hbox1.addWidget(QLabel("Mode:"))
        self.combo_plot_mode = QComboBox()
        self.combo_plot_mode.addItems(["All (3 Subplots)", "Total Only", "Spin-Up Only", "Spin-Down Only"])
        self.combo_plot_mode.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        hbox1.addWidget(self.combo_plot_mode)
        layout.addLayout(hbox1)

        self.chk_show_center = QCheckBox("Show εd line")
        self.chk_show_center.setChecked(False)
        self.chk_show_center.stateChanged.connect(lambda *args: self.real_time_update.emit())
        layout.addWidget(self.chk_show_center)

    def _on_system_activated(self, index):
        label = self.combo_system.itemText(index)
        if label:
            self.system_changed.emit(label)

    def update_systems(self, labels, current_label=None):
        self.combo_system.blockSignals(True)
        self.combo_system.clear()
        if labels:
            self.combo_system.addItems(labels)
            if current_label and current_label in labels:
                self.combo_system.setCurrentText(current_label)
        self.combo_system.blockSignals(False)

    def set_current_system(self, label):
        self.combo_system.blockSignals(True)
        if label:
            self.combo_system.setCurrentText(label)
        self.combo_system.blockSignals(False)

class PDOSStyleDialog(FloatingConfigDialog):
    real_time_update = Signal()

    def __init__(self, parent=None):
        super().__init__(title="Style Settings", parent=parent)
        self._build_ui()

    def _build_ui(self):
        layout = self.content_layout

        hbox1 = QHBoxLayout()
        hbox1.addWidget(QLabel("Theme:"))
        self.combo_theme = QComboBox()
        dos_themes = list(THEMES_CONFIG.get("5_color_dos", {}).keys())
        if dos_themes:
            self.combo_theme.addItems(dos_themes)
        self.combo_theme.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        hbox1.addWidget(self.combo_theme)
        layout.addLayout(hbox1)

        self.btn_color = QPushButton("🎨 Colors")
        layout.addWidget(self.btn_color)

        self.chk_fill = QCheckBox("Fill")
        self.chk_fill.setChecked(True)
        self.chk_fill.stateChanged.connect(lambda *args: self.real_time_update.emit())
        layout.addWidget(self.chk_fill)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(QLabel("Alpha:"))
        self.spin_alpha = QDoubleSpinBox()
        self.spin_alpha.setRange(0.0, 1.0)
        self.spin_alpha.setSingleStep(0.1)
        self.spin_alpha.setValue(0.5)
        self.spin_alpha.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox2.addWidget(self.spin_alpha)
        layout.addLayout(hbox2)

        hbox3 = QHBoxLayout()
        hbox3.addWidget(QLabel("LW:"))
        self.spin_lw = QDoubleSpinBox()
        self.spin_lw.setRange(0.5, 5.0)
        self.spin_lw.setSingleStep(0.5)
        self.spin_lw.setValue(1.0)
        self.spin_lw.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox3.addWidget(self.spin_lw)
        layout.addLayout(hbox3)
