from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QWidget
from PySide6.QtCore import Qt, Signal

class FloatingConfigDialog(QDialog):
    """
    Base class for floating, modeless configuration dialogs.
    It automatically adds 'Apply' and 'Close' buttons, and emits
    the `applied` signal when 'Apply' is clicked.
    """
    applied = Signal()

    def __init__(self, title="Settings", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("FloatingConfigDialog")
        
        # Set to be a tool window or standard non-modal window.
        # Qt.Tool keeps it floating but allows interacting with the main window.
        self.setWindowFlags(Qt.Window | Qt.Tool)
        
        # Ensures it does not block the main window
        self.setModal(False)
        
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setSpacing(10)
        
        # Content placeholder for subclasses
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.addWidget(self.content_widget)
        
        # Apply / Close button box
        self.btn_box = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        self.btn_box.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)
        self.btn_box.button(QDialogButtonBox.Close).clicked.connect(self.close)
        
        self._main_layout.addStretch()
        self._main_layout.addWidget(self.btn_box)
        
    def _on_apply(self):
        self.applied.emit()
