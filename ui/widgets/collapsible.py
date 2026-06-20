"""
Collapsible widget for grouping UI elements.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QSizePolicy
from PySide6.QtCore import Qt

class CollapsibleWidget(QWidget):
    """A widget with a toggle button that shows/hides its content area."""
    
    def __init__(self, title="", parent=None, is_expanded=False):
        super().__init__(parent)
        
        self.toggle_button = QToolButton(self)
        self.toggle_button.setText(f"\u25bc {title}" if is_expanded else f"\u25b6 {title}")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(is_expanded)
        self.toggle_button.setStyleSheet("""
            QToolButton { 
                border: none; 
                font-weight: bold; 
                text-align: left;
                padding: 4px;
            }
        """)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.content_area = QWidget()
        self.content_area.setVisible(is_expanded)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(10, 5, 0, 0)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        
        self.toggle_button.toggled.connect(self._on_toggle)

    def add_widget(self, widget):
        """Add a widget to the collapsible content area."""
        self.content_layout.addWidget(widget)
        
    def add_layout(self, layout):
        """Add a layout to the collapsible content area."""
        self.content_layout.addLayout(layout)

    def _on_toggle(self, checked):
        title = self.toggle_button.text()[2:]  # Remove the icon part
        self.toggle_button.setText(f"\u25bc {title}" if checked else f"\u25b6 {title}")
        self.content_area.setVisible(checked)
