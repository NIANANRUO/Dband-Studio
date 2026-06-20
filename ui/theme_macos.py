"""
macOS-like Glassmorphism Theme.
Focuses on neutral, low-saturation colors with high contrast for tabs/buttons.
"""

LIGHT_GLASS_QSS = """
/* Global Font & Background */
QWidget {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
    color: #1C1C1E;
}

QMainWindow, QDialog, QWidget#FloatingConfigDialog {
    background-color: #F2F2F7; /* macOS light mode background */
}

/* QListWidget and QTreeView */
QListView, QListWidget, QTreeView {
    background-color: #FFFFFF;
    color: #1C1C1E;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 8px;
    padding: 2px;
}
QListView::item:selected, QListWidget::item:selected, QTreeView::item:selected {
    background-color: #E5E5EA; /* Light slate/gray selection instead of blue */
    color: #1C1C1E;
    border-radius: 4px;
}
QListView::item:hover, QListWidget::item:hover {
    background-color: #F2F2F7;
    border-radius: 4px;
}

/* GroupBox and Left Cards (White Float Cards) */
QGroupBox, QFrame#LeftCard {
    background-color: rgba(255, 255, 255, 0.7); /* Frosted glass */
    border: 1px solid rgba(0, 0, 0, 0.06);
    border-bottom: 1px solid rgba(0, 0, 0, 0.15); /* Drop shadow simulation */
    border-radius: 10px;
    margin-top: 2.5ex;
}
QFrame#LeftCard {
    margin-top: 0; 
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: #333333;
    font-weight: 600; /* SemiBold */
    font-size: 13px;
    left: 10px;
}

/* Tabs: Independent Semi-transparent glass cards */
QTabWidget::pane {
    border: 1px solid rgba(0, 0, 0, 0.06);
    background-color: #FFFFFF;
    border-radius: 8px;
    top: -1px; /* Align perfectly with active tab */
}

QTabBar {
    background-color: transparent;
}

QTabBar::tab {
    background-color: rgba(255, 255, 255, 0.5); /* Semi-transparent unselected */
    color: #555555;
    padding: 6px 16px;
    margin-right: 6px;
    margin-bottom: 4px; /* Space between tab and pane */
    border: 1px solid rgba(0, 0, 0, 0.05);
    border-bottom: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: 8px; /* Fully rounded cards */
}

QTabBar::tab:disabled {
    color: #A0A0A0;
    background-color: transparent;
    border: 1px solid transparent;
}

QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #1C1C1E;
    font-weight: bold;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-bottom: 2px solid rgba(0, 0, 0, 0.15); /* Popped up state */
}

QTabBar::tab:hover:!selected {
    background-color: rgba(255, 255, 255, 0.8);
    color: #48484A;
}

/* Buttons: Glassmorphism Defaults */
QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.9), stop:1 rgba(245, 245, 250, 0.6));
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-top: 1px solid rgba(255, 255, 255, 1);
    border-bottom: 1px solid rgba(0, 0, 0, 0.15);
    border-radius: 6px;
    padding: 6px 16px;
    color: #1C1C1E;
    font-size: 13px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 1), stop:1 rgba(250, 250, 255, 0.8));
    border: 1px solid rgba(0, 0, 0, 0.15);
}

QPushButton:pressed {
    background-color: rgba(0, 0, 0, 0.03);
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-top: 1px solid rgba(0, 0, 0, 0.18);
    border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

QPushButton:disabled {
    background-color: transparent;
    color: #999999;
    border: 1px solid rgba(0, 0, 0, 0.08);
}

/* Prominent Action Buttons */
QPushButton[isPrimary="true"] {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(100, 116, 139, 0.9), stop:1 rgba(71, 85, 105, 0.9));
    color: #FFFFFF;
    border: 1px solid rgba(0, 0, 0, 0.4);
    border-top: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 6px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton[isPrimary="true"]:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(100, 116, 139, 0.9), stop:1 rgba(71, 85, 105, 0.9));
}
QPushButton[isPrimary="true"]:pressed {
    background-color: rgba(30, 41, 59, 0.95);
    border-top: 1px solid rgba(0, 0, 0, 0.3);
}

/* Inputs */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background-color: rgba(255, 255, 255, 0.5); /* Light glass inset */
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-top: 1px solid rgba(0, 0, 0, 0.12); /* Inset shadow */
    border-bottom: 1px solid rgba(255, 255, 255, 0.8); /* Bottom highlight */
    border-radius: 6px;
    padding: 4px 8px;
    color: #1C1C1E;
    font-size: 13px;
    selection-background-color: #E2E8F0;
    selection-color: #1C1C1E;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #1C1C1E;
    selection-background-color: #F1F5F9;
    selection-color: #1C1C1E;
    border: 1px solid rgba(0,0,0,0.1);
    border-radius: 6px;
}

QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    background-color: #FFFFFF;
    border: 1px solid #94A3B8; /* Slate focus ring */
}

/* Splitter */
QSplitter::handle {
    background-color: transparent;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #C7C7CC;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #AEAEB2;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    border: none;
    background: transparent;
    height: 10px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #C7C7CC;
    min-width: 20px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: #AEAEB2;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Table Widget */
QTableWidget, QTableView {
    border: none;
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    color: #1C1C1E;
    gridline-color: rgba(0, 0, 0, 0.03); /* Extremely faint grid lines */
}
QHeaderView::section {
    background-color: #FFFFFF;
    color: #64748B; /* Secondary text color */
    border: none;
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
    padding: 6px 4px;
    font-weight: bold;
    font-size: 12px;
}
QTableView::item:selected {
    background-color: #F1F5F9; /* Very soft slate selection */
    color: #1C1C1E;
}

/* Menu Bar & Menus */
QMenuBar {
    background-color: #F2F2F7;
    color: #1C1C1E;
    font-size: 14px;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
}
QMenuBar::item:selected {
    background: rgba(0,0,0,0.05);
    border-radius: 4px;
}
QMenu {
    background-color: #FFFFFF;
    color: #1C1C1E;
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: 6px;
    font-size: 14px;
}
QMenu::item {
    padding: 6px 24px 6px 20px;
}
QMenu::item:selected {
    background-color: #E2E8F0;
    color: #1C1C1E;
}

/* ScrollArea Backgrounds */
QScrollArea {
    background-color: transparent;
    border: none;
}
QWidget#scrollContent {
    background-color: transparent;
}
"""

DARK_GLASS_QSS = """
/* Global Font & Background */
QWidget {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
    color: #E0E0E0;
}

QMainWindow, QDialog, QWidget#FloatingConfigDialog {
    background-color: #1E1E1E; /* macOS dark mode background */
}

/* QListWidget and QTreeView */
QListView, QListWidget, QTreeView {
    background-color: #1E1E1E;
    color: #E0E0E0;
    border: 1px solid #3A3A3C;
}
QListView::item:selected, QListWidget::item:selected, QTreeView::item:selected {
    background-color: #475569;
    color: #FFFFFF;
}

/* GroupBox and Left Cards */
QGroupBox, QFrame#LeftCard {
    background-color: rgba(40, 40, 40, 0.6); /* Frosted dark glass */
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-bottom: 1px solid rgba(0, 0, 0, 0.3);
    border-radius: 10px;
    margin-top: 2.5ex; /* leave space for title */
}
QFrame#LeftCard {
    margin-top: 0; /* Left cards don't have built-in groupbox titles */
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: #E0E0E0;
    font-weight: 600; /* SemiBold */
    font-size: 13px;
    left: 10px;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #3A3A3C;
    background-color: #252525;
    border-radius: 8px;
}

QTabBar::tab {
    background-color: #1E1E1E;
    color: #888888;
    padding: 8px 20px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid transparent;
}

QTabBar::tab:disabled {
    color: #555555;
    background-color: transparent;
}

QTabBar::tab:selected {
    background-color: #252525;
    color: #E0E0E0;
    font-weight: bold;
    border: 1px solid #3A3A3C;
    border-bottom-color: #252525;
}

QTabBar::tab:hover:!selected {
    background-color: #333333;
    color: #A0A0A5;
}

/* High Contrast Buttons */
QPushButton {
    background-color: #2C2C2E;
    border: 1px solid #3A3A3C;
    border-radius: 6px;
    padding: 6px 16px;
    color: #E0E0E0;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #3A3A3C;
    border: 1px solid #555555;
}

QPushButton:pressed {
    background-color: #1C1C1E;
}

QPushButton:disabled {
    background-color: transparent;
    color: #666666;
    border: 1px solid #333333;
}

/* Prominent Action Buttons */
QPushButton[isPrimary="true"] {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(100, 116, 139, 0.9), stop:1 rgba(71, 85, 105, 0.9));
    color: #FFFFFF;
    border: 1px solid rgba(0, 0, 0, 0.4);
    border-top: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 6px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton[isPrimary="true"]:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(116, 132, 155, 0.9), stop:1 rgba(81, 95, 115, 0.9));
}
QPushButton[isPrimary="true"]:pressed {
    background-color: rgba(30, 41, 59, 0.95);
    border-top: 1px solid rgba(0, 0, 0, 0.3);
}
QPushButton[isPrimary="true"]:disabled {
    background-color: #333333;
    color: #555555;
    border: none;
}

/* Inputs */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background-color: rgba(0, 0, 0, 0.15); /* Deep inset glass */
    border: 1px solid rgba(0, 0, 0, 0.3);
    border-top: 1px solid rgba(0, 0, 0, 0.4);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 4px 8px;
    color: #E0E0E0;
    font-size: 13px;
    selection-background-color: #475569;
    selection-color: #FFFFFF;
}

QComboBox QAbstractItemView {
    background-color: #252525;
    color: #E0E0E0;
    selection-background-color: #475569;
}

QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #555555;
    background-color: #252525;
}

/* Splitter */
QSplitter::handle {
    background-color: transparent;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #48484A;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #636366;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    border: none;
    background: transparent;
    height: 10px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #48484A;
    min-width: 20px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: #636366;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* QTableWidget inside Tabs (Unified Dark Color) */
QTableWidget {
    border: none;
    background-color: #1E1E1E;
    alternate-background-color: #1E1E1E;
    color: #E0E0E0;
    gridline-color: #333333;
}
QHeaderView::section {
    background-color: #1E1E1E;
    color: #A0A0A5;
    border: none;
    border-bottom: 1px solid #333333;
    padding: 4px;
    font-weight: bold;
}
QTableView::item:selected {
    background-color: #3A3A3C;
    color: #FFFFFF;
}

/* Menu Bar & Menus */
QMenuBar {
    background-color: #1E1E1E;
    color: #E0E0E0;
    font-size: 14px;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
}
QMenuBar::item:selected {
    background: #333333;
    border-radius: 4px;
}
QMenu {
    background-color: #252525;
    color: #E0E0E0;
    border: 1px solid #3A3A3C;
    border-radius: 6px;
    font-size: 14px;
}
QMenu::item {
    padding: 6px 24px 6px 20px;
}
QMenu::item:selected {
    background-color: #0A84FF;
    color: #FFFFFF;
}

/* ScrollArea Backgrounds */
QScrollArea {
    background-color: transparent;
    border: none;
}
QWidget#scrollContent {
    background-color: transparent;
}
"""
