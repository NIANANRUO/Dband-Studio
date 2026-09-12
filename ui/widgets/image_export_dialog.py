"""Batch image export options for the main application window."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)
from ui.i18n import combo_value


@dataclass(frozen=True)
class ImageExportOptions:
    output_directory: Path
    image_format: str
    dpi: int
    system_labels: tuple[str, ...]
    include_individual_pdos: bool
    include_bar_chart: bool
    include_multi_pdos: bool


class ImageExportDialog(QDialog):
    """Collect batch scope, destination, format, and resolution."""

    def __init__(self, labels, initial_directory, has_summary, has_multi,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Export Images")
        self.resize(680, 520)
        self._build_ui(labels, initial_directory, has_summary, has_multi)

    def _build_ui(self, labels, initial_directory, has_summary, has_multi):
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Export every analyzed system with the current PDOS style and axes settings.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(str(initial_directory))
        self.folder_edit.setPlaceholderText("Choose an output folder")
        folder_row.addWidget(self.folder_edit, 1)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse)
        folder_row.addWidget(browse_button)
        layout.addWidget(QLabel("Output folder:"))
        layout.addLayout(folder_row)

        form = QFormLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "PDF", "SVG"])
        form.addRow("Format:", self.format_combo)
        self.dpi_combo = QComboBox()
        self.dpi_combo.addItems(["300", "600"])
        form.addRow("Resolution (DPI):", self.dpi_combo)
        layout.addLayout(form)

        self.individual_check = QCheckBox("Individual PDOS image for each selected system")
        self.individual_check.setChecked(bool(labels))
        self.individual_check.setEnabled(bool(labels))
        self.individual_check.toggled.connect(self._sync_system_list_enabled)
        layout.addWidget(self.individual_check)

        self.system_list = QListWidget()
        for label in labels:
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.system_list.addItem(item)
        self.system_list.setEnabled(bool(labels))
        layout.addWidget(self.system_list, 1)

        selection_row = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._set_all_systems(Qt.Checked))
        selection_row.addWidget(select_all)
        select_none = QPushButton("Clear")
        select_none.clicked.connect(lambda: self._set_all_systems(Qt.Unchecked))
        selection_row.addWidget(select_none)
        selection_row.addStretch()
        layout.addLayout(selection_row)

        self.bar_check = QCheckBox("D-band center summary bar chart")
        self.bar_check.setChecked(has_summary)
        self.bar_check.setEnabled(has_summary)
        layout.addWidget(self.bar_check)

        self.multi_check = QCheckBox("Current multi-system PDOS comparison")
        self.multi_check.setChecked(has_multi)
        self.multi_check.setEnabled(has_multi)
        layout.addWidget(self.multi_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.button(QDialogButtonBox.Save).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        start = self.folder_edit.text().strip()
        if start and not Path(start).exists():
            start = str(Path(start).parent)
        selected = QFileDialog.getExistingDirectory(
            self, "Choose Export Folder", start)
        if selected:
            self.folder_edit.setText(selected)

    def _set_all_systems(self, state):
        for index in range(self.system_list.count()):
            self.system_list.item(index).setCheckState(state)

    def _sync_system_list_enabled(self, enabled):
        self.system_list.setEnabled(enabled)

    def selected_labels(self):
        return tuple(
            self.system_list.item(index).text()
            for index in range(self.system_list.count())
            if self.system_list.item(index).checkState() == Qt.Checked
        )

    def accept(self):
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "Missing Folder", "Choose an output folder.")
            return
        if (self.individual_check.isChecked() and not self.selected_labels()
                and not self.bar_check.isChecked()
                and not self.multi_check.isChecked()):
            QMessageBox.warning(self, "Nothing Selected", "Select at least one image to export.")
            return
        if not (self.individual_check.isChecked() or self.bar_check.isChecked()
                or self.multi_check.isChecked()):
            QMessageBox.warning(self, "Nothing Selected", "Select at least one image to export.")
            return
        super().accept()

    def options(self):
        return ImageExportOptions(
            output_directory=Path(self.folder_edit.text().strip()),
            image_format=combo_value(self.format_combo).lower(),
            dpi=int(combo_value(self.dpi_combo)),
            system_labels=self.selected_labels(),
            include_individual_pdos=self.individual_check.isChecked(),
            include_bar_chart=self.bar_check.isChecked(),
            include_multi_pdos=self.multi_check.isChecked(),
        )
