"""
File management panel: file type selection, add/remove/rename/clear, file list table.
"""
import os
import glob

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QInputDialog, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


class FileManagerPanel(QFrame):
    """Left-side panel for managing data source files."""

    files_changed = Signal()               # emitted when file list changes
    label_renamed = Signal(str, str)       # old_label, new_label
    clear_requested = Signal()             # emitted when user clicks Clear All

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setObjectName("LeftCard")
        self.state = state
        self._is_dark_mode = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title_lbl = QLabel("1. Data Source")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #333333;")
        layout.addWidget(title_lbl)

        # File type selector
        row_type = QHBoxLayout()
        row_type.addWidget(QLabel("Type:"))
        self.combo_type = QComboBox()
        self.combo_type.addItems(["Auto Detect", "vasprun.xml", "DOSCAR", "VASPKIT PDOS"])
        self.combo_type.setFixedHeight(24)
        row_type.addWidget(self.combo_type, 1)
        layout.addLayout(row_type)

        # Buttons grid
        grid = QGridLayout()
        grid.setSpacing(4)

        btn_add = QPushButton("\U0001f4c2 Add Files")
        btn_add.setFixedHeight(26)
        btn_add.clicked.connect(self.add_files)
        grid.addWidget(btn_add, 0, 0)

        btn_folder = QPushButton("\U0001f4c1 Add Folder")
        btn_folder.setFixedHeight(26)
        btn_folder.clicked.connect(self.add_folder)
        grid.addWidget(btn_folder, 0, 1)

        btn_rm = QPushButton("Remove")
        btn_rm.setFixedHeight(26)
        btn_rm.clicked.connect(self.remove_selected)
        grid.addWidget(btn_rm, 1, 0)

        btn_rn = QPushButton("Rename")
        btn_rn.setFixedHeight(26)
        btn_rn.clicked.connect(self.rename_file)
        grid.addWidget(btn_rn, 1, 1)

        btn_cl = QPushButton("Clear All")
        btn_cl.setFixedHeight(26)
        btn_cl.clicked.connect(self.clear_files)
        grid.addWidget(btn_cl, 2, 0, 1, 2)

        layout.addLayout(grid)

        # File list table
        self.list_files = QTableWidget(0, 2)
        self.list_files.setHorizontalHeaderLabels(["#", "System Label"])
        self.list_files.horizontalHeader().setToolTip("Double-click the System Label to rename it")
        self.list_files.verticalHeader().setVisible(False)
        self.list_files.setShowGrid(False)
        self._apply_list_stylesheet()
        self.list_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.list_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.list_files.setFixedHeight(140)
        self.list_files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.list_files.itemChanged.connect(self._on_label_edited)
        layout.addWidget(self.list_files)

    def get_file_type(self):
        return self.combo_type.currentText()

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", "All Files (*)")
        if files:
            self.import_paths(files)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not d:
            return
        found = []
        for pattern in ["vasprun.xml", "DOSCAR", "PDOS_*.dat", "PDOS_*.txt"]:
            found.extend(glob.glob(os.path.join(d, "**", pattern), recursive=True))
        if not found:
            QMessageBox.information(self, "Info",
                                    "No vasprun.xml / DOSCAR / PDOS_* files found in this folder.")
            return
        self.import_paths(found)

    def import_paths(self, paths):
        existing_labels = {e["label"] for e in self.state.file_entries}
        for f in paths:
            if not os.path.isfile(f):
                continue
            base = os.path.basename(f)
            label = base
            if label in existing_labels:
                parent = os.path.basename(os.path.dirname(f))
                label = f"{parent}/{base}"
                c = 2
                orig = label
                while label in existing_labels:
                    label = f"{orig} ({c})"
                    c += 1
            self.state.file_entries.append({"path": f, "label": label, "atoms": ""})
            existing_labels.add(label)
        self._refresh_file_list()
        self.files_changed.emit()

    def _refresh_file_list(self):
        self.list_files.blockSignals(True)
        self.list_files.setRowCount(len(self.state.file_entries))
        for i, e in enumerate(self.state.file_entries):
            idx_item = QTableWidgetItem(str(i + 1))
            idx_item.setFlags(idx_item.flags() & ~Qt.ItemIsEditable)
            idx_item.setTextAlignment(Qt.AlignCenter)
            self.list_files.setItem(i, 0, idx_item)
            
            lbl = QTableWidgetItem(e["label"])
            lbl.setToolTip(e["path"])
            self.list_files.setItem(i, 1, lbl)
        self.list_files.blockSignals(False)

    def _on_label_edited(self, item):
        r, c = item.row(), item.column()
        if c == 1 and 0 <= r < len(self.state.file_entries):
            t = item.text().strip()
            old = self.state.file_entries[r]["label"]
            if t and t != old:
                self.state.file_entries[r]["label"] = t
                self.label_renamed.emit(old, t)
            else:
                self.list_files.blockSignals(True)
                item.setText(old)
                self.list_files.blockSignals(False)

    def rename_file(self):
        rows = self.list_files.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Info", "Select a file row first.")
            return
        r = rows[0].row()
        old = self.state.file_entries[r]["label"]
        new, ok = QInputDialog.getText(self, "Rename Label", "New label:", text=old)
        if ok and new.strip() and new.strip() != old:
            new_label = new.strip()
            self.state.file_entries[r]["label"] = new_label
            self._refresh_file_list()
            self.label_renamed.emit(old, new_label)

    def remove_selected(self):
        rows = sorted({idx.row() for idx in self.list_files.selectionModel().selectedRows()},
                      reverse=True)
        for r in rows:
            if 0 <= r < len(self.state.file_entries):
                del self.state.file_entries[r]
        self._refresh_file_list()
        self.files_changed.emit()

    def clear_files(self):
        self.state.file_entries.clear()
        self.list_files.setRowCount(0)
        self.clear_requested.emit()

    def _restore_entries(self, entries):
        """Restore file entries from a saved workspace (used by MainWindow)."""
        self.state.file_entries = list(entries)
        self._refresh_file_list()
        self.files_changed.emit()

    def set_dark_mode(self, is_dark):
        self._is_dark_mode = is_dark
        self._apply_list_stylesheet()
        
    def _apply_list_stylesheet(self):
        # Delegate styling entirely to global theme_macos.py
        pass
