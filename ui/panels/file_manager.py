"""
File management panel: file type selection, add/remove/rename/clear, file list table.
"""
import os
import glob
from dataclasses import asdict

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QApplication, QFileDialog, QMessageBox, QInputDialog, QHeaderView,
    QAbstractItemView, QMenu,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor

from core.exceptions import AmbiguousLayoutError, DbandError
from core.loader import DataLoader
from core.pdos_metadata import input_context_from_entry


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
        row_type.addWidget(self.combo_type, 1)
        layout.addLayout(row_type)

        # Buttons grid
        grid = QGridLayout()
        grid.setSpacing(4)

        btn_add = QPushButton("\U0001f4c2 Add Files")
        btn_add.clicked.connect(self.add_files)
        grid.addWidget(btn_add, 0, 0)

        btn_folder = QPushButton("\U0001f4c1 Add Folder")
        btn_folder.clicked.connect(self.add_folder)
        grid.addWidget(btn_folder, 0, 1)

        btn_rm = QPushButton("Remove")
        btn_rm.clicked.connect(self.remove_selected)
        grid.addWidget(btn_rm, 1, 0)

        btn_rn = QPushButton("Rename")
        btn_rn.clicked.connect(self.rename_file)
        grid.addWidget(btn_rn, 1, 1)

        btn_cl = QPushButton("Clear All")
        btn_cl.clicked.connect(self.clear_files)
        grid.addWidget(btn_cl, 2, 0, 1, 2)

        self.btn_copy = QPushButton("Copy Details")
        self.btn_copy.setToolTip("Copy the selected file's import diagnosis for issue reports")
        self.btn_copy.clicked.connect(self.copy_selected_details)
        grid.addWidget(self.btn_copy, 3, 0)

        btn_aux = QPushButton("Aux Files")
        btn_aux.setToolTip("Select auxiliary files that DBand Studio is authorized to read")
        aux_menu = QMenu(btn_aux)
        aux_menu.addAction("Select Structure...", lambda: self.choose_auxiliary_file("structure"))
        aux_menu.addAction("Select Metadata...", lambda: self.choose_auxiliary_file("metadata"))
        aux_menu.addAction("Select Spin Partner...", lambda: self.choose_auxiliary_file("spin_partner"))
        aux_menu.addSeparator()
        aux_menu.addAction("Remove Auxiliary Files", self.clear_auxiliary_files)
        btn_aux.setMenu(aux_menu)
        grid.addWidget(btn_aux, 3, 1)

        layout.addLayout(grid)

        # File list table
        self.list_files = QTableWidget(0, 3)
        self.list_files.setHorizontalHeaderLabels(["#", "System Label", "Data"])
        self.list_files.horizontalHeader().setToolTip("Double-click the System Label to rename it")
        self.list_files.verticalHeader().setVisible(False)
        self.list_files.setShowGrid(False)
        self._apply_list_stylesheet()
        self.list_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.list_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.list_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.list_files.setFixedHeight(140)
        self.list_files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.list_files.itemChanged.connect(self._on_label_edited)
        self.list_files.itemSelectionChanged.connect(self._update_selected_diagnostic)
        layout.addWidget(self.list_files)

        self.lbl_diagnostic = QLabel("No file selected.")
        self.lbl_diagnostic.setWordWrap(True)
        self.lbl_diagnostic.setMinimumHeight(34)
        self.lbl_diagnostic.setStyleSheet(
            "font-size: 10px; color: #555555; padding: 2px 4px;")
        layout.addWidget(self.lbl_diagnostic)

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
            entry = {
                "path": f, "label": label, "atoms": "",
                "capabilities": None, "inspection_error": "",
                "inspection_status": "not_checked",
                "auxiliary_files": {
                    "structure": None, "metadata": None, "spin_partner": None,
                },
            }
            self._inspect_entry(entry)
            self.state.file_entries.append(entry)
            existing_labels.add(label)
        self._refresh_file_list()
        if self.state.file_entries:
            self.lbl_diagnostic.setText(
                self._diagnostic_text(self.state.file_entries[-1]))
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

            capabilities = e.get("capabilities") or {}
            error = e.get("inspection_error", "")
            inspection_status = e.get("inspection_status", "not_checked")
            if inspection_status == "needs_input":
                status = QTableWidgetItem("Needs input")
                status.setForeground(QColor("#B26A00"))
                status.setToolTip(error)
            elif error:
                status = QTableWidgetItem("Blocked")
                status.setForeground(QColor("#C62828"))
                status.setToolTip(error)
            elif capabilities:
                resolution = capabilities.get("orbital_resolution", "unknown")
                status = QTableWidgetItem(f"Ready · {resolution}")
                available = ", ".join(capabilities.get("available_orbitals", ()))
                warnings = "\n".join(capabilities.get("warnings", ()))
                details = (
                    f"Format: {capabilities.get('source_format', 'unknown')}\n"
                    f"Spin: {capabilities.get('spin_mode', 'unknown')}\n"
                    f"Orbitals: {available or 'none'}")
                if warnings:
                    details += f"\nWarnings:\n{warnings}"
                status.setToolTip(details)
                status.setForeground(QColor("#2E7D32"))
            else:
                status = QTableWidgetItem("Not checked")
                status.setToolTip("This entry predates import preflight; re-add it to inspect.")
            status.setFlags(status.flags() & ~Qt.ItemIsEditable)
            self.list_files.setItem(i, 2, status)
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

    def _inspect_entry(self, entry):
        declared = self.get_file_type()
        try:
            if declared == "Auto Detect":
                source_format = DataLoader.detect(entry["path"])
            else:
                source_format = declared
            context = input_context_from_entry(entry, source_format)
            capabilities = DataLoader.inspect(context)
            entry["capabilities"] = asdict(capabilities)
            entry["inspection_error"] = ""
            entry["inspection_status"] = "ready"
        except AmbiguousLayoutError as exc:
            entry["capabilities"] = None
            entry["inspection_error"] = str(exc)
            entry["inspection_status"] = "needs_input"
        except (DbandError, OSError, ValueError) as exc:
            entry["capabilities"] = None
            entry["inspection_error"] = str(exc)
            entry["inspection_status"] = "blocked"

    def _selected_row(self):
        rows = self.list_files.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    @staticmethod
    def _diagnostic_text(entry):
        status = entry.get("inspection_status", "not_checked")
        auxiliary = entry.get("auxiliary_files") or {}
        authorized = [
            f"{kind}={os.path.basename(path)}"
            for kind, path in auxiliary.items() if path]
        suffix = f" Authorized: {', '.join(authorized)}." if authorized else ""
        if entry.get("inspection_error"):
            return (
                f"{status.replace('_', ' ').title()}: "
                f"{entry['inspection_error']}{suffix}")
        capabilities = entry.get("capabilities") or {}
        return (
            f"Ready: {capabilities.get('source_format', 'unknown')}, "
            f"{capabilities.get('spin_mode', 'unknown')} spin, "
            f"{capabilities.get('orbital_resolution', 'unknown')} projection."
            f"{suffix}")

    def _update_selected_diagnostic(self):
        row = self._selected_row()
        if row is not None:
            self.lbl_diagnostic.setText(
                self._diagnostic_text(self.state.file_entries[row]))

    def choose_auxiliary_file(self, kind):
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "Info", "Select a file row first.")
            return
        titles = {
            "structure": "Select POSCAR/CONTCAR",
            "metadata": "Select INCAR or vasprun.xml",
            "spin_partner": "Select Spin Partner PDOS",
        }
        path, _ = QFileDialog.getOpenFileName(self, titles[kind], "", "All Files (*)")
        if path:
            self.set_auxiliary_file(row, kind, path)

    def set_auxiliary_file(self, row, kind, path):
        entry = self.state.file_entries[row]
        auxiliary = entry.setdefault("auxiliary_files", {})
        auxiliary[kind] = path
        self._inspect_entry(entry)
        self._refresh_file_list()
        self.lbl_diagnostic.setText(self._diagnostic_text(entry))
        self.files_changed.emit()

    def clear_auxiliary_files(self):
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "Info", "Select a file row first.")
            return
        entry = self.state.file_entries[row]
        entry["auxiliary_files"] = {
            "structure": None, "metadata": None, "spin_partner": None}
        self._inspect_entry(entry)
        self._refresh_file_list()
        self.lbl_diagnostic.setText(self._diagnostic_text(entry))
        self.files_changed.emit()

    def copy_selected_details(self):
        rows = self.list_files.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Info", "Select a file row first.")
            return
        entry = self.state.file_entries[rows[0].row()]
        capabilities = entry.get("capabilities") or {}
        lines = [f"File: {entry.get('path', '')}", f"Label: {entry.get('label', '')}"]
        if entry.get("inspection_error"):
            lines.append(f"Status: Blocked\nReason: {entry['inspection_error']}")
        else:
            lines.extend([
                "Status: Ready",
                f"Format: {capabilities.get('source_format', 'unknown')}",
                f"VASP version: {capabilities.get('vasp_version') or 'not reported'}",
                f"Spin: {capabilities.get('spin_mode', 'unknown')}",
                f"Projection: {capabilities.get('orbital_resolution', 'unknown')}",
                "Orbitals: " + ", ".join(capabilities.get("available_orbitals", ())),
            ])
            warnings = capabilities.get("warnings", ())
            if warnings:
                lines.append("Warnings: " + " | ".join(warnings))
        auxiliary = entry.get("auxiliary_files") or {}
        lines.extend([
            f"Authorized structure: {auxiliary.get('structure') or 'none'}",
            f"Authorized metadata: {auxiliary.get('metadata') or 'none'}",
            f"Authorized spin partner: {auxiliary.get('spin_partner') or 'none'}",
        ])
        QApplication.clipboard().setText("\n".join(lines))
        self.btn_copy.setText("Copied")
        self.btn_copy.setStyleSheet("color: #FFFFFF; background-color: #2E7D32;")
        self.lbl_diagnostic.setText(
            "Copied import details to the clipboard.")
        self.lbl_diagnostic.setStyleSheet(
            "font-size: 10px; color: #1B5E20; padding: 2px 4px; font-weight: bold;")
        QTimer.singleShot(2200, self._restore_copy_feedback)

    def _restore_copy_feedback(self):
        self.btn_copy.setText("Copy Details")
        self.btn_copy.setStyleSheet("")
        self.lbl_diagnostic.setStyleSheet(
            "font-size: 10px; color: #555555; padding: 2px 4px;")
        self._update_selected_diagnostic()

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
