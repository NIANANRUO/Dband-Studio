"""
DBand Studio
============================
Entry point for the application.

Architecture (v4.0):
- services layer, MemoryAwareLRU, hybridization worker
- Auto-loads parser plugins from plugins/ directory on startup
- Version is resolved from a single source (pyproject.toml) via
  utils.helpers.get_app_version(); do not hard-code version strings.
"""
import sys
import os
import logging

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from utils.styling import init_matplotlib
from utils.helpers import get_app_version
from ui.main_window import MainWindow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


def runtime_preflight():
    """Load and exercise every binary dependency required by release builds.

    This path deliberately creates no QApplication, so the frozen executable
    can be checked non-interactively in CI or before sharing an installer.
    An import-only check is insufficient for SciPy because some extension
    modules are loaded only when the numerical function is called.
    """
    import numpy as np
    from scipy.integrate import simpson
    from scipy.special import erf
    from pymatgen.core import Element
    from lxml import etree
    from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    integral = simpson(np.array([0.0, 1.0, 4.0]), x=np.array([0.0, 1.0, 2.0]))
    if not np.isfinite(integral):
        raise RuntimeError("SciPy Simpson preflight returned a non-finite value.")
    if not np.isfinite(erf(1.0)):
        raise RuntimeError("SciPy special-function preflight returned a non-finite value.")
    if Element("Mo").Z != 42:
        raise RuntimeError("pymatgen periodic-table data preflight failed.")
    if etree.fromstring(b"<vasprun/>").tag != "vasprun":
        raise RuntimeError("lxml XML preflight failed.")
    if not all((QtCore, QtGui, QtSvg, QtWidgets)):
        raise RuntimeError("PySide6 Qt runtime preflight failed.")
    if FigureCanvasQTAgg is None or Figure is None:
        raise RuntimeError("Matplotlib Qt backend preflight failed.")


def main():
    if "--runtime-self-check" in sys.argv:
        runtime_preflight()
        return 0

    # QApplication must be created before any QWidget
    app = QApplication(sys.argv)
    
    # Set modern base style and apply macOS QSS
    app.setStyle("Fusion")
    from ui.theme_macos import LIGHT_GLASS_QSS
    app.setStyleSheet(LIGHT_GLASS_QSS)
    
    # Set application icon (warn if missing, but don't crash)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        logging.getLogger("main").warning("Icon file not found: %s", icon_path)

    # Show Splash Screen
    from ui.splash_screen import CustomSplashScreen
    import time
    splash = CustomSplashScreen()
    splash.show()

    splash.update_progress(10, "Initializing Matplotlib engine...")
    init_matplotlib()
    time.sleep(0.4)  # 视觉缓冲

    splash.update_progress(40, "Scanning for external plugins...")
    from core.plugins import PluginLoader
    loaded = PluginLoader.load_all()
    if loaded:
        logging.getLogger("main").info(
            "Loaded %d plugin(s): %s", len(loaded), ", ".join(loaded))
    time.sleep(0.4)  # 视觉缓冲

    splash.update_progress(70, "Building UI components...")
    win = MainWindow()
    time.sleep(0.4)  # 视觉缓冲

    splash.update_progress(100, "Starting DBand Studio...")
    # 进度条跑满后稍作停留
    time.sleep(0.4)

    splash.close()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
