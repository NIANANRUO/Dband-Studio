from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QLabel, QLineEdit, QPushButton, QDialogButtonBox
)
from PySide6.QtCore import Qt

class AtomsConfigDialog(QDialog):
    """Dialog for configuring target atoms for each imported system independently."""
    
    def __init__(self, file_entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Target Atoms per System")
        self.setMinimumWidth(500)
        self.setMinimumHeight(350)
        
        self.file_entries = file_entries
        self.inputs = {} # label -> QLineEdit
        
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        info = QLabel("Leave the input blank to use the global Target Atoms setting.")
        info.setStyleSheet("color: #666; font-style: italic; margin-bottom: 5px;")
        layout.addWidget(info)
        
        # Scroll area for the systems list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setSpacing(10)
        
        for entry in self.file_entries:
            label = entry["label"]
            atoms = entry.get("atoms", "")
            
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setMinimumWidth(180)
            
            line_edit = QLineEdit()
            line_edit.setText(atoms)
            line_edit.setPlaceholderText("Global Default")
            self.inputs[label] = line_edit
            
            btn_clear = QPushButton("Clear")
            btn_clear.setFixedWidth(60)
            btn_clear.clicked.connect(lambda checked, le=line_edit: le.clear())
            
            row.addWidget(lbl)
            row.addWidget(line_edit, 1)
            row.addWidget(btn_clear)
            
            self.content_layout.addLayout(row)
            
        self.content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        # Bottom controls
        bottom_row = QHBoxLayout()
        btn_clear_all = QPushButton("Clear All")
        btn_clear_all.clicked.connect(self._clear_all)
        bottom_row.addWidget(btn_clear_all)
        
        bottom_row.addStretch()
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        bottom_row.addWidget(btn_box)
        
        layout.addLayout(bottom_row)
        
    def _clear_all(self):
        """Clear all input fields."""
        for le in self.inputs.values():
            le.clear()
            
    def apply_updates(self):
        """Apply the inputs back to the file_entries dict."""
        for entry in self.file_entries:
            label = entry["label"]
            if label in self.inputs:
                entry["atoms"] = self.inputs[label].text().strip()
