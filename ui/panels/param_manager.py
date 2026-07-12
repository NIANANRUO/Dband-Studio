"""
Calculation parameters panel: atoms, spin mode, integration range.
"""
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QRadioButton, QCheckBox, QButtonGroup, QPushButton,
    QComboBox,
)
from PySide6.QtCore import Qt


class ParamManagerPanel(QFrame):
    """Left-side panel for configuring calculation parameters."""

    def __init__(self, state=None, parent=None):
        super().__init__(parent)
        self.setObjectName("LeftCard")
        self.state = state
        self.setFrameShape(QFrame.StyledPanel)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title_lbl = QLabel("2. Calculation Parameters")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #333333;")
        layout.addWidget(title_lbl)

        lbl_layout = QHBoxLayout()
        lbl_layout.addWidget(QLabel("Target Atoms (e.g. 1,2,5-8 or Fe):"))
        lbl_layout.addStretch()
        btn_config = QPushButton("⚙️ Configure")
        btn_config.setToolTip("Configure Target Atoms for each system independently")
        btn_config.clicked.connect(self._open_atoms_config)
        lbl_layout.addWidget(btn_config)
        layout.addLayout(lbl_layout)
        
        self.entry_atoms = QLineEdit()
        self.entry_atoms.setPlaceholderText("Global Default (leave blank for all)")
        layout.addWidget(self.entry_atoms)

        layout.addWidget(QLabel("Spin Mode:"))
        srow = QHBoxLayout()
        self.spin_group = QButtonGroup(self)
        self.radio_tot = QRadioButton("Total")
        self.radio_up = QRadioButton("Spin-Up")
        self.radio_dn = QRadioButton("Spin-Down")
        self.radio_tot.setChecked(True)
        self.spin_group.addButton(self.radio_tot, 1)
        self.spin_group.addButton(self.radio_up, 2)
        self.spin_group.addButton(self.radio_dn, 3)
        for r in (self.radio_tot, self.radio_up, self.radio_dn):
            srow.addWidget(r)
        layout.addLayout(srow)

        layout.addWidget(QLabel("Integration Range:"))
        self.chk_all = QCheckBox("All Energy Range")
        self.chk_all.setChecked(True)
        self.chk_fermi = QCheckBox("Below Fermi Level (\u2264 Ef)")
        self.chk_fermi.setChecked(True)
        self.chk_custom = QCheckBox("Custom Range (rel. to Ef):")
        layout.addWidget(self.chk_all)
        layout.addWidget(self.chk_fermi)
        layout.addWidget(self.chk_custom)

        cr = QHBoxLayout()
        cr.addWidget(QLabel("Emin:"))
        self.entry_emin = QLineEdit("-8")
        self.entry_emin.setFixedWidth(55)
        cr.addWidget(self.entry_emin)
        cr.addWidget(QLabel("Emax:"))
        self.entry_emax = QLineEdit("0")
        self.entry_emax.setFixedWidth(55)
        cr.addWidget(self.entry_emax)
        cr.addWidget(QLabel("eV"))
        cr.addStretch()
        layout.addLayout(cr)

        # Integration method selection
        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("Integration:"))
        self.combo_method = QComboBox()
        self.combo_method.addItems(["Trapezoid (NumPy)", "Simpson (SciPy)"])
        self.combo_method.setCurrentIndex(0)  # Default: Trapezoid
        self.combo_method.setToolTip(
            "Trapezoid: fast, NumPy only. Simpson: an independent higher-order "
            "quadrature rule requiring SciPy. Different software may use different "
            "grid-boundary and integration conventions."
        )
        method_row.addWidget(self.combo_method)
        method_row.addStretch()
        layout.addLayout(method_row)

    def _open_atoms_config(self):
        from PySide6.QtWidgets import QMessageBox
        if not self.state or not self.state.file_entries:
            QMessageBox.information(self, "Info", "Please import files first.")
            return
        from ui.widgets.atoms_config_dialog import AtomsConfigDialog
        dlg = AtomsConfigDialog(self.state.file_entries, self)
        if dlg.exec():
            dlg.apply_updates()

    def get_spin_mode(self):
        if self.radio_tot.isChecked():
            return "total"
        if self.radio_up.isChecked():
            return "up"
        return "down"

    def get_atoms_text(self):
        return self.entry_atoms.text()

    def get_range_config(self):
        """Returns (do_all, do_fermi, do_custom, custom_range_or_None)."""
        do_all = self.chk_all.isChecked()
        do_fermi = self.chk_fermi.isChecked()
        do_custom = self.chk_custom.isChecked()
        custom_range = None
        if do_custom:
            try:
                emin = float(self.entry_emin.text())
                emax = float(self.entry_emax.text())
                if emin < emax:
                    custom_range = (emin, emax)
            except ValueError:
                pass
        return do_all, do_fermi, do_custom, custom_range

    def get_integration_method(self) -> str:
        """Return ``'trapezoid'`` or ``'simpson'``."""
        idx = self.combo_method.currentIndex()
        return "simpson" if idx == 1 else "trapezoid"
