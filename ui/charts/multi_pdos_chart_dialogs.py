from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QCheckBox, QSpinBox, QDoubleSpinBox, QPushButton
)
from PySide6.QtCore import Qt, Signal
from ui.widgets.floating_dialog_base import FloatingConfigDialog
from ui.widgets.checkable_combo import CheckableComboBox
from core.parsers.constants import d_orb_names

class MultiPDOSDataDialog(FloatingConfigDialog):
    real_time_update = Signal()

    def __init__(self, parent=None):
        super().__init__(title="Data Control", parent=parent)
        self._build_ui()

    def _build_ui(self):
        layout = self.content_layout

        hbox1 = QHBoxLayout()
        hbox1.addWidget(QLabel("Systems:"))
        self.combo_systems = CheckableComboBox()
        self.combo_systems.setProperty("_i18n_skip_items", True)
        self.combo_systems.setMinimumWidth(150)
        self.combo_systems.selection_changed.connect(lambda *args: self.real_time_update.emit())
        hbox1.addWidget(self.combo_systems)
        layout.addLayout(hbox1)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(QLabel("Orbital:"))
        self.combo_orbital = QComboBox()
        self.combo_orbital.addItems(["Total d-DOS"] + list(d_orb_names))
        self.combo_orbital.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        hbox2.addWidget(self.combo_orbital)
        layout.addLayout(hbox2)

        hbox3 = QHBoxLayout()
        hbox3.addWidget(QLabel("Spin:"))
        self.combo_spin_mode = QComboBox()
        self.combo_spin_mode.addItems(["Total (Up+Down)", "Spin Up", "Spin Down"])
        self.combo_spin_mode.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        hbox3.addWidget(self.combo_spin_mode)
        layout.addLayout(hbox3)

        self.chk_show_center = QCheckBox("Show εd line")
        self.chk_show_center.setChecked(False)
        self.chk_show_center.stateChanged.connect(lambda *args: self.real_time_update.emit())
        layout.addWidget(self.chk_show_center)

        self.combo_center_ref = QComboBox()
        self.combo_center_ref.addItem("All Selected Systems")
        self.combo_center_ref.setEnabled(False)
        self.chk_show_center.stateChanged.connect(lambda s: self.combo_center_ref.setEnabled(s == Qt.Checked))
        self.combo_center_ref.currentIndexChanged.connect(lambda *args: self.real_time_update.emit())
        layout.addWidget(self.combo_center_ref)


class MultiPDOSStyleDialog(FloatingConfigDialog):
    real_time_update = Signal()

    def __init__(self, parent=None):
        super().__init__(title="Style Settings", parent=parent)
        self._build_ui()

    def _build_ui(self):
        layout = self.content_layout

        self.btn_colors = QPushButton("🎨 Set Colors")
        layout.addWidget(self.btn_colors)

        self.chk_fill = QCheckBox("Fill")
        self.chk_fill.setChecked(True)
        self.chk_fill.stateChanged.connect(lambda *args: self.real_time_update.emit())
        layout.addWidget(self.chk_fill)

        hbox1 = QHBoxLayout()
        hbox1.addWidget(QLabel("Alpha:"))
        self.spin_alpha = QDoubleSpinBox()
        self.spin_alpha.setRange(0.0, 1.0)
        self.spin_alpha.setSingleStep(0.1)
        self.spin_alpha.setValue(0.3)
        self.spin_alpha.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox1.addWidget(self.spin_alpha)
        layout.addLayout(hbox1)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(QLabel("LW:"))
        self.spin_lw = QDoubleSpinBox()
        self.spin_lw.setRange(0.5, 5.0)
        self.spin_lw.setSingleStep(0.5)
        self.spin_lw.setValue(1.5)
        self.spin_lw.valueChanged.connect(lambda *args: self.real_time_update.emit())
        hbox2.addWidget(self.spin_lw)
        layout.addLayout(hbox2)
