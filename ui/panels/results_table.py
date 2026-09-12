"""
Results data table with Times New Roman styling and highlight columns.
"""
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QVBoxLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from core.parsers import d_orb_names
from utils.styling import (
    RESULTS_TABLE_QSS, RESULTS_TABLE_QSS_DARK,
    TABLE_HEADER_BG, TABLE_HEADER_BG_DARK,
    TABLE_BG_META, TABLE_BG_META_DARK,
    TABLE_BG_BASIC, TABLE_BG_BASIC_DARK,
    TABLE_BG_WEIGHTS, TABLE_BG_WEIGHTS_DARK,
    TABLE_BG_CENTERS, TABLE_BG_CENTERS_DARK,
)


class ResultsTableWidget(QWidget):
    """Right-side results table with styling and d-band center highlighting."""

    row_selected = Signal(str, str)  # emits (label, range_name) when a row is selected

    SUB_HEADERS = [
        "Label", "Range", "εd (eV)", "Width (eV)", "Filling%",
        "dxy%", "dyz%", "dz²%", "dxz%", "dx²-y²%",
        "dxy", "dyz", "dz²", "dxz", "dx²-y²",
    ]

    def __init__(self, orb_colors=None, parent=None):
        super().__init__(parent)
        self.orb_colors = orb_colors or {}
        self._is_dark_mode = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Header Table ---
        self.header_table = QTableWidget()
        self.header_table.setObjectName("ResultsHeaderTable")
        self.header_table.setColumnCount(15)
        self.header_table.setRowCount(2)

        self.header_table.horizontalHeader().setVisible(False)
        self.header_table.verticalHeader().setVisible(False)
        self.header_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.header_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.header_table.setFocusPolicy(Qt.NoFocus)
        self.header_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.header_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Main Headers
        self.header_table.setSpan(0, 0, 2, 1)
        self.header_table.setItem(0, 0, QTableWidgetItem("Label"))
        
        self.header_table.setSpan(0, 1, 2, 1)
        self.header_table.setItem(0, 1, QTableWidgetItem("Range"))
        
        self.header_table.setSpan(0, 2, 1, 3)
        self.header_table.setItem(0, 2, QTableWidgetItem("Basic Properties"))
        
        self.header_table.setSpan(0, 5, 1, 5)
        self.header_table.setItem(0, 11, QTableWidgetItem("Orbital Weights (%)"))
        
        self.header_table.setSpan(0, 10, 1, 5)
        self.header_table.setItem(0, 16, QTableWidgetItem("Orbital Centers (\u03b5d_orb, eV)"))

        # Sub Headers
        for i, text in enumerate(self.SUB_HEADERS):
            if i >= 2:
                self.header_table.setItem(1, i, QTableWidgetItem(text))

        # Style header cells
        header_bg = QColor(TABLE_HEADER_BG)
        for r in range(2):
            for c in range(15):
                item = self.header_table.item(r, c)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(header_bg)

        self.header_table.setFixedHeight(65)
        self.header_table.setStyleSheet(RESULTS_TABLE_QSS)

        # --- Data Table ---
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(15)
        self.data_table.horizontalHeader().setVisible(False)
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.data_table.setSortingEnabled(True)
        self.data_table.setAlternatingRowColors(False)
        self.data_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.data_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.data_table.setStyleSheet(RESULTS_TABLE_QSS)
        
        layout.addWidget(self.header_table)
        layout.addWidget(self.data_table)

        # Sync scrolling and column widths
        self.data_table.horizontalScrollBar().valueChanged.connect(
            self.header_table.horizontalScrollBar().setValue)
        self.header_table.horizontalScrollBar().valueChanged.connect(
            self.data_table.horizontalScrollBar().setValue)
        
        # Important: Allow data_table sections to be resized, and sync header_table
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.data_table.horizontalHeader().sectionResized.connect(self._on_section_resized)
        
        # When header_table sections are resized, sync data_table (so user can drag header!)
        self.header_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.header_table.horizontalHeader().sectionResized.connect(self._on_header_section_resized)
        
        self.data_table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # Set explicit widths to prevent header truncation
        widths = [180, 60, 75, 85, 75] + [65]*5 + [70]*5
        for c in range(15):
            if c == 0:
                self.data_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
                self.header_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
            else:
                self.data_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Interactive)
                self.header_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Interactive)
                self.header_table.setColumnWidth(c, widths[c])
                self.data_table.setColumnWidth(c, widths[c])

    def _on_section_resized(self, logicalIndex, oldSize, newSize):
        # Prevent infinite loops by blocking signals temporarily
        self.header_table.horizontalHeader().blockSignals(True)
        self.header_table.setColumnWidth(logicalIndex, newSize)
        self.header_table.horizontalHeader().blockSignals(False)

    def _on_header_section_resized(self, logicalIndex, oldSize, newSize):
        self.data_table.horizontalHeader().blockSignals(True)
        self.data_table.setColumnWidth(logicalIndex, newSize)
        self.data_table.horizontalHeader().blockSignals(False)

    def set_dark_mode(self, is_dark):
        self._is_dark_mode = is_dark
        qss = RESULTS_TABLE_QSS_DARK if is_dark else RESULTS_TABLE_QSS
        self.header_table.setStyleSheet(qss)
        self.data_table.setStyleSheet(qss)
        
        # update header background
        header_bg = QColor(TABLE_HEADER_BG_DARK if is_dark else TABLE_HEADER_BG)
        header_fg = Qt.white if is_dark else QColor("#333333")
        for r in range(2):
            for c in range(15):
                item = self.header_table.item(r, c)
                if item:
                    item.setBackground(header_bg)
                    item.setForeground(header_fg)

        # Update data table cells
        if self._is_dark_mode:
            bg_meta = [QColor(TABLE_BG_META_DARK[0]), QColor(TABLE_BG_META_DARK[1])]
            bg_basic = [QColor(TABLE_BG_BASIC_DARK[0]), QColor(TABLE_BG_BASIC_DARK[1])]
            bg_weights = [QColor(TABLE_BG_WEIGHTS_DARK[0]), QColor(TABLE_BG_WEIGHTS_DARK[1])]
            bg_centers = [QColor(TABLE_BG_CENTERS_DARK[0]), QColor(TABLE_BG_CENTERS_DARK[1])]
            fg_color = Qt.white
        else:
            bg_meta = [QColor(TABLE_BG_META[0]), QColor(TABLE_BG_META[1])]
            bg_basic = [QColor(TABLE_BG_BASIC[0]), QColor(TABLE_BG_BASIC[1])]
            bg_weights = [QColor(TABLE_BG_WEIGHTS[0]), QColor(TABLE_BG_WEIGHTS[1]).lighter(110)]
            bg_centers = [QColor(TABLE_BG_CENTERS[0]), QColor(TABLE_BG_CENTERS[1])]
            fg_color = Qt.black

        for r in range(self.data_table.rowCount()):
            is_odd = (r % 2 == 1)
            idx = 1 if is_odd else 0
            for c in range(15):
                item = self.data_table.item(r, c)
                if item:
                    if c < 2:
                        bg = bg_meta[idx]
                    elif 2 <= c <= 4:
                        bg = bg_basic[idx]
                    elif 5 <= c <= 9:
                        bg = bg_weights[idx]
                    else:
                        bg = bg_centers[idx]
                    item.setBackground(bg)
                    item.setForeground(fg_color)

    def setRowCount(self, count):
        self.data_table.setRowCount(count)

    def selectRow(self, row):
        self.data_table.selectRow(row)

    def _on_selection_changed(self, selected, _deselected):
        idxs = selected.indexes()
        if not idxs:
            return
        row = idxs[0].row()
        label_item = self.data_table.item(row, 0)
        range_item = self.data_table.item(row, 1)
        if label_item and range_item:
            self.row_selected.emit(label_item.text(), range_item.text())

    def populate(self, results_data):
        """Clear and repopulate table from results_data list."""
        self.data_table.setSortingEnabled(False)
        self.data_table.setRowCount(0)
        
        # Color palettes for different zones [EvenRow, OddRow]
        if self._is_dark_mode:
            bg_meta = [QColor(TABLE_BG_META_DARK[0]), QColor(TABLE_BG_META_DARK[1])]
            bg_basic = [QColor(TABLE_BG_BASIC_DARK[0]), QColor(TABLE_BG_BASIC_DARK[1])]
            bg_weights = [QColor(TABLE_BG_WEIGHTS_DARK[0]), QColor(TABLE_BG_WEIGHTS_DARK[1])]
            bg_centers = [QColor(TABLE_BG_CENTERS_DARK[0]), QColor(TABLE_BG_CENTERS_DARK[1])]
            fg_color = Qt.white
        else:
            bg_meta = [QColor(TABLE_BG_META[0]), QColor(TABLE_BG_META[1])]
            bg_basic = [QColor(TABLE_BG_BASIC[0]), QColor(TABLE_BG_BASIC[1])]
            bg_weights = [QColor(TABLE_BG_WEIGHTS[0]), QColor(TABLE_BG_WEIGHTS[1]).lighter(110)]
            bg_centers = [QColor(TABLE_BG_CENTERS[0]), QColor(TABLE_BG_CENTERS[1])]
            fg_color = QColor("#333333")

        # Reset header colors to standard (in case they were colored previously)
        for i in range(5, 15):
            item = self.header_table.item(1, i)
            if item:
                item.setForeground(fg_color)

        for rd in results_data:
            row = self.data_table.rowCount()
            self.data_table.insertRow(row)

            vals = [
                rd.label, rd.range_name,
                f"{rd.center:.4f}" if np.isfinite(rd.center) else "NaN",
                f"{rd.width:.4f}" if np.isfinite(rd.width) else "NaN",
                f"{rd.filling:.1f}" if np.isfinite(rd.filling) else "NaN",
            ]
            if rd.is_aggregate_d:
                # LORBIT=10 has one physical d-total channel, not five
                # components.  Keep the table schema stable while showing
                # unavailable m-resolved values honestly.
                vals.extend(["—"] * len(d_orb_names))
                vals.extend(["—"] * len(d_orb_names))
            else:
                for o in d_orb_names:
                    vals.append(f"{rd.orb_weights.get(o, 0):.1f}%")
                for o in d_orb_names:
                    c = rd.orb_centers.get(o, float('nan'))
                    vals.append(f"{c:.4f}" if np.isfinite(c) else "NaN")

            for ci, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if ci == 0:
                    version = rd.vasp_version or "not reported"
                    item.setToolTip(
                        f"Source: {rd.source_format}\nVASP: {version}\n"
                        f"Spin: {rd.spin_mode}\nProjection: {rd.orbital_resolution}\n"
                        f"Fields: {rd.field_source}\nIntegration: {rd.integration_method}\n"
                        f"Structure: {rd.structure_source}\nMetadata: {rd.metadata_source}\n"
                        f"SAXIS: {rd.saxis_source}")
                
                # Striping and grouping logic
                is_odd = (row % 2 == 1)
                idx = 1 if is_odd else 0
                
                if ci < 2:
                    bg = bg_meta[idx]
                elif 2 <= ci <= 4:
                    bg = bg_basic[idx]
                elif 5 <= ci <= 9:
                    bg = bg_weights[idx]
                else:
                    bg = bg_centers[idx]

                item.setBackground(bg)
                if self._is_dark_mode:
                    item.setForeground(Qt.white)

                if ci >= 2:
                    try:
                        clean = v.replace("%", "").strip()
                        # NaN/inf are valid floats but sort unpredictably — map to large sentinel
                        if clean.lower() in ("nan", "inf", "-inf"):
                            item.setData(Qt.UserRole, 1e308 if clean.lower() != "-inf" else -1e308)
                        else:
                            item.setData(Qt.UserRole, float(clean))
                    except ValueError:
                        item.setData(Qt.UserRole, float("inf"))
                    
                self.data_table.setItem(row, ci, item)

        self.data_table.setSortingEnabled(True)

    def update_label(self, old_label, new_label):
        """Update label text in-place after rename."""
        self.data_table.setSortingEnabled(False)
        for row in range(self.data_table.rowCount()):
            item = self.data_table.item(row, 0)
            if item and item.text() == old_label:
                item.setText(new_label)
        self.data_table.setSortingEnabled(True)
