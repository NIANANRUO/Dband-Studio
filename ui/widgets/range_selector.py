"""
Reusable range selector widget (min/max QLineEdit pair + label).

Used in PDOS chart toolbar and Hybridization plot settings to avoid
duplicated X/Y range input code.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)
from PySide6.QtCore import Signal
from typing import Optional, Tuple


class RangeSelectorWidget(QWidget):
    """Min/Max numeric range input with optional apply button.

    Signals:
        range_changed(float|None, float|None) — emitted on return/apply.
    """

    range_changed = Signal(object, object)  # (min_val, max_val) — None = no input

    def __init__(self, label: str = "Range:", show_apply: bool = True, parent=None):
        super().__init__(parent)
        self._show_apply = show_apply
        self._build_ui(label)

    def _build_ui(self, label):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(label))

        self.entry_min = QLineEdit()
        self.entry_min.setPlaceholderText("Min")
        self.entry_min.setFixedWidth(50)
        self.entry_min.returnPressed.connect(self._emit_range)
        layout.addWidget(self.entry_min)

        layout.addWidget(QLabel("to"))
        self.entry_max = QLineEdit()
        self.entry_max.setPlaceholderText("Max")
        self.entry_max.setFixedWidth(50)
        self.entry_max.returnPressed.connect(self._emit_range)
        layout.addWidget(self.entry_max)

        if self._show_apply:
            self.btn_apply = QPushButton("Apply")
            self.btn_apply.setFixedHeight(24)
            self.btn_apply.clicked.connect(self._emit_range)
            layout.addWidget(self.btn_apply)

        layout.addStretch()

    def _emit_range(self):
        self.range_changed.emit(*self.get_range())

    def get_range(self) -> Tuple[Optional[float], Optional[float]]:
        """Parse current input values. Returns (None, None) for empty fields."""
        vmin, vmax = None, None
        try:
            t = self.entry_min.text().strip()
            if t:
                vmin = float(t)
        except ValueError:
            pass
        try:
            t = self.entry_max.text().strip()
            if t:
                vmax = float(t)
        except ValueError:
            pass
        return vmin, vmax

    def set_range(self, vmin: Optional[float], vmax: Optional[float]):
        """Set input fields programmatically."""
        self.entry_min.setText("" if vmin is None else str(vmin))
        self.entry_max.setText("" if vmax is None else str(vmax))
