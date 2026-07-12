"""Font-aware sizing helpers for compact desktop controls."""

from PySide6.QtWidgets import QAbstractButton, QComboBox, QWidget


def ensure_compact_controls_fit_text(container: QWidget) -> None:
    """Set minimum dimensions without preventing layouts from growing controls."""
    controls = [*container.findChildren(QAbstractButton), *container.findChildren(QComboBox)]
    for control in controls:
        text = control.text() if isinstance(control, QAbstractButton) else control.currentText()
        if not text:
            continue
        metrics = control.fontMetrics()
        horizontal_padding = 30 if isinstance(control, QAbstractButton) else 44
        control.setMinimumWidth(
            max(control.minimumWidth(), metrics.horizontalAdvance(text.replace("&", "")) + horizontal_padding)
        )
        control.setMinimumHeight(max(control.minimumHeight(), metrics.height() + 10))

