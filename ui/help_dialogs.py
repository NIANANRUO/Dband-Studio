from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QScrollArea, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap, QIcon

from utils.helpers import get_app_version

class DocumentationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Documentation - DBand Studio")
        self.setMinimumSize(650, 550)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content_widget = QWidget()
        scroll.setWidget(content_widget)
        
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(15)
        
        title = QLabel("DBand Studio User Guide")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(title)
        
        content_layout.addSpacing(10)
        
        docs_text = """
<style>
    h3 { color: #0A84FF; margin-bottom: 5px; font-family: 'Segoe UI', sans-serif; }
    p, li { font-size: 14px; line-height: 1.6; font-family: 'Segoe UI', sans-serif; }
    code { background-color: rgba(128, 128, 128, 0.2); padding: 2px 5px; border-radius: 4px; font-family: 'Consolas', monospace; }
</style>

<h3>1. Target Atoms</h3>
<p>Specify the atomic indices you want to extract and analyze. For example, entering <code>1,2,3-5</code> will parse atoms 1, 2, 3, 4, and 5.<br>
If you leave this field empty, the system will automatically parse the projected density of states (PDOS) for <b>all atoms</b> in the system.</p>

<h3>2. Spin Configuration</h3>
<ul>
    <li><b>Total (Spin-Up + Spin-Down)</b>: Adds the spin-up and spin-down DOS together to calculate the total d-band center.</li>
    <li><b>Spin-Up Only</b>: Extracts and analyzes only the majority spin (up) electronic states.</li>
    <li><b>Spin-Down Only</b>: Extracts and analyzes only the minority spin (down) electronic states.</li>
</ul>

<h3>3. Integration Range</h3>
<p>Determines the energy integration window [E_min, E_max] used to calculate the d-band center.</p>
<ul>
    <li><b>All Energy Range</b>: Integrates over the entire energy range provided in the data.</li>
    <li><b>Below Fermi Level (&lt; Ef)</b>: Integrates only the occupied states (below the Fermi level).</li>
    <li><b>Custom Range</b>: Allows you to manually input precise upper and lower bounds (relative to the Fermi level, E_f = 0 eV).</li>
</ul>

<h3>4. Chart & Style Control</h3>
<p>In the top-right corner of each advanced chart tab (PDOS Curves, Hybridization Analysis, etc.), you will find floating buttons for <b>Data Control</b> and <b>Style Settings</b>.<br>Here, you can freely switch preset theme colors, change axis ranges, adjust fill opacities, and export publication-quality high-resolution charts with a single click.</p>
"""
        lbl_text = QLabel(docs_text)
        lbl_text.setWordWrap(True)
        lbl_text.setTextFormat(Qt.RichText)
        content_layout.addWidget(lbl_text)
        content_layout.addStretch()
        
        layout.addWidget(scroll)
        
        # Bottom button bar
        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(20, 10, 20, 20)
        
        btn_close = QPushButton("Close")
        btn_close.setMinimumHeight(32)
        btn_close.setFixedWidth(150)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        btn_layout.addStretch()
        
        layout.addWidget(btn_bar)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About DBand Studio")
        self.setFixedSize(550, 480)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 30)
        layout.setSpacing(10)
        
        # Logo 
        lbl_logo = QLabel("🌌")
        lbl_logo.setFont(QFont("Segoe UI Emoji", 56))
        lbl_logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_logo)
        
        # Title & Version
        lbl_title = QLabel("DBand Studio")
        lbl_title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_title)
        
        lbl_version = QLabel(f"Version v{get_app_version()}")
        lbl_version.setFont(QFont("Segoe UI", 11))
        lbl_version.setAlignment(Qt.AlignCenter)
        lbl_version.setStyleSheet("color: #0A84FF; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(lbl_version)
        
        # Separation Line
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #D0D0D0;")
        layout.addWidget(line)
        layout.addSpacing(10)
        
        # Description
        desc_text = (
            "<p style='text-align: center; font-size: 13px; line-height: 1.5; font-family: \"Segoe UI\", sans-serif;'>"
            "A focused, professional, and aesthetic toolkit for scientific data processing.<br>"
            "Dedicated to providing top-tier VASP d-band center analysis, 3D visualization of<br>orbital hybridization, and efficient electronic structure data processing workflows."
            "</p>"
        )
        lbl_desc = QLabel(desc_text)
        lbl_desc.setWordWrap(True)
        lbl_desc.setTextFormat(Qt.RichText)
        lbl_desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_desc)
        
        layout.addSpacing(10)
        
        # Ownership Statement
        owner_text = (
            "<div style='background-color: rgba(10, 132, 255, 0.08); padding: 15px; border-radius: 8px; border: 1px solid rgba(10, 132, 255, 0.2);'>"
            "<p style='font-size: 12px; line-height: 1.6; text-align: justify; margin: 0; font-family: \"Segoe UI\", sans-serif;'>"
            "<b>© 2026 Nian an. All rights reserved.</b><br><br>"
            "This software is independently conceived, developed, and maintained by <b>Nian an</b>. The author (Nian an) retains <b>100% absolute ownership, control, and all intellectual property rights</b> over this software, its underlying source code, and derivative algorithms. "
            "Unauthorized distribution, reverse engineering, or commercial use in any form is strictly prohibited without explicit authorization."
            "</p></div>"
        )
        lbl_owner = QLabel(owner_text)
        lbl_owner.setWordWrap(True)
        lbl_owner.setTextFormat(Qt.RichText)
        layout.addWidget(lbl_owner)
        
        layout.addSpacing(5)
        
        # Contact info
        lbl_contact = QLabel("Author: <b>Nian an</b> &nbsp;&nbsp;|&nbsp;&nbsp; Email: <a href='mailto:2148316923@qq.com' style='color: #0A84FF; text-decoration: none;'>2148316923@qq.com</a>")
        lbl_contact.setOpenExternalLinks(True)
        lbl_contact.setAlignment(Qt.AlignCenter)
        lbl_contact.setFont(QFont("Segoe UI", 11))
        layout.addWidget(lbl_contact)
        
        layout.addStretch()
        
        # Close Button
        btn_close = QPushButton("OK")
        btn_close.setMinimumHeight(32)
        btn_close.setFixedWidth(120)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        
        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(btn_close)
        hbox.addStretch()
        layout.addLayout(hbox)
