import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGraphicsDropShadowEffect, 
                               QFrame, QApplication)
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPixmap, QColor, QPainter, QPen, QConicalGradient

class SmoothSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.timer.start(16)  # ~60fps

    def rotate(self):
        self.angle = (self.angle + 8) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(5, 5, self.width() - 10, self.height() - 10)
        
        # Create a contrasting warm gradient against the blue/dark background
        gradient = QConicalGradient(rect.center(), -self.angle)
        gradient.setColorAt(0, QColor(255, 149, 0, 255))   # Bright Neon Orange
        gradient.setColorAt(0.4, QColor(255, 204, 0, 200)) # Golden Yellow
        gradient.setColorAt(1, QColor(255, 204, 0, 0))

        pen = QPen(gradient, 4) # Thicker ring for better visibility
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        
        # Draw the arc
        painter.drawArc(rect, 0, 360 * 16)


class CustomSplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        # Frameless window, transparent background, always on top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 350)

        self._setup_ui()

    def _setup_ui(self):
        # 1. Background Frame (Rounded corners with blurry crystal background)
        self.bg_frame = QFrame(self)
        self.bg_frame.setGeometry(0, 0, 500, 350)
        
        bg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "splash_bg.png")
        bg_path_url = bg_path.replace("\\", "/")  # Ensure valid URL for QSS
        
        if os.path.exists(bg_path):
            self.bg_frame.setStyleSheet(f"""
                QFrame {{
                    background-image: url({bg_path_url});
                    background-position: center;
                    background-repeat: no-repeat;
                    border-radius: 15px;
                }}
            """)
        else:
            # Fallback if image not found
            self.bg_frame.setStyleSheet("""
                QFrame {
                    background-color: #0F172A;
                    border-radius: 15px;
                }
            """)

        # 2. Glass Card (Frosted glass overlay)
        self.glass_card = QFrame(self.bg_frame)
        self.glass_card.setGeometry(100, 40, 300, 270)
        self.glass_card.setStyleSheet("""
            QFrame {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(25, 35, 50, 140), stop:1 rgba(15, 20, 30, 80)); /* Textured dark gradient */
                border-top: 1px solid rgba(255, 255, 255, 50);
                border-left: 1px solid rgba(255, 255, 255, 30);
                border-right: 1px solid rgba(255, 255, 255, 10);
                border-bottom: 1px solid rgba(255, 255, 255, 10);
                border-radius: 12px;
            }
        """)

        # Drop shadow for the glass card to make it float
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.glass_card.setGraphicsEffect(shadow)

        # 3. Main layout inside the glass card
        layout = QVBoxLayout(self.glass_card)
        layout.setContentsMargins(30, 30, 30, 20)
        layout.setSpacing(8)

        # Logo
        self.logo_label = QLabel(self.glass_card)
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.logo_label)

        layout.addSpacing(5)

        # Title
        self.title_label = QLabel("DBand Studio", self.glass_card)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: 900; font-family: 'Segoe UI', 'Inter', Arial; border: none; background: transparent;")
        layout.addWidget(self.title_label)

        # Version
        from utils.helpers import get_app_version
        self.version_label = QLabel(f"v{get_app_version()}", self.glass_card)
        self.version_label.setAlignment(Qt.AlignCenter)
        self.version_label.setStyleSheet("color: #F8FAFC; font-size: 14px; font-weight: bold; font-family: 'Segoe UI', 'Inter', Arial; border: none; background: transparent;")
        layout.addWidget(self.version_label)

        layout.addStretch()

        # Spinner Layout (Center align)
        spinner_layout = QVBoxLayout()
        spinner_layout.setAlignment(Qt.AlignCenter)
        self.spinner = SmoothSpinner(self.glass_card)
        self.spinner.setStyleSheet("border: none; background: transparent;")
        spinner_layout.addWidget(self.spinner)
        layout.addLayout(spinner_layout)

        # Status Label
        self.status_label = QLabel("Initializing...", self.glass_card)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #F8FAFC; font-size: 12px; font-weight: 700; font-family: 'Segoe UI', 'Inter', Arial; padding-top: 5px; border: none; background: transparent;")
        layout.addWidget(self.status_label)

    def update_progress(self, value: int, message: str):
        # The spinner doesn't use the integer value, but we update the text
        self.status_label.setText(message)
        QApplication.processEvents()
