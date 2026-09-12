"""
Global styling configuration for matplotlib and Qt widgets.
"""
import matplotlib
import matplotlib.transforms as mtransforms
import json
import os
import numpy as np

def load_themes_config():
    """Load themes from external config/themes.json."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "themes.json")
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load themes.json: {e}")
    return {}

THEMES_CONFIG = load_themes_config()


def init_matplotlib():
    """Set Times New Roman as default for all matplotlib charts."""
    matplotlib.rcParams['font.family'] = 'serif'
    matplotlib.rcParams['font.serif'] = ['Times New Roman', 'SimSun', 'Arial Unicode MS', 'DejaVu Serif']
    matplotlib.rcParams['mathtext.fontset'] = 'stix'
    matplotlib.rcParams['axes.unicode_minus'] = False
    matplotlib.rcParams['savefig.dpi'] = 600  # Default export resolution


# Default orbital colors for d-band PDOS
_default_5_color = THEMES_CONFIG.get("5_color_dos", {}).get("Default Material", ["#E91E63", "#2196F3", "#4CAF50", "#FF9800", "#9C27B0"])
DEFAULT_D_COLORS = {
    "dxy": _default_5_color[0], "dyz": _default_5_color[1], "dz2": _default_5_color[2],
    "dxz": _default_5_color[3], "dx2-y2": _default_5_color[4],
}

# QSS for the results table
RESULTS_TABLE_QSS = """
    QTableWidget {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 13px;
        gridline-color: rgba(0, 0, 0, 0.03); /* Faint grid */
        border: none;
    }
    QHeaderView::section {
        background-color: #FFFFFF;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-weight: bold;
        font-size: 12px;
        color: #64748B;
        border: none;
        border-bottom: 1px solid rgba(0,0,0,0.08);
        padding: 4px;
    }
    QTableView::item:selected, QTableView::item:selected:!active {
        background-color: #F1F5F9; /* Slate selection */
        color: #1C1C1E;
    }
"""

RESULTS_TABLE_QSS_DARK = """
    QTableWidget {
        font-family: 'Times New Roman';
        font-size: 10pt;
        gridline-color: #444444;
        background-color: transparent;
        color: #E0E0E0;
    }
    QHeaderView::section {
        background-color: #2B2B2B;
        font-family: 'Times New Roman';
        font-weight: bold;
        font-size: 10pt;
        border: 1px solid #444444;
        padding: 4px;
        color: #E0E0E0;
    }
    QTableView::item:selected, QTableView::item:selected:!active {
        background-color: rgba(10, 132, 255, 0.3);
        color: #FFFFFF;
    }
"""

# PDOS center line styling
CENTER_COLOR = "#D32F2F"
CENTER_LW = 1.3
CENTER_FONTSIZE = 7.5

# Hybridization plot colors
HYB_FRAG1_COLOR = "#E91E63"       # Fragment 1 (Metal) fill and line
HYB_FRAG2_COLOR = "#2196F3"       # Fragment 2 (Ligand) fill and line
HYB_METAL_CENTER_COLOR = "#C62828"  # Metal center line (darker red)
HYB_LIGAND_CENTER_COLOR = "#1565C0"  # Ligand center line (darker blue)

# UI button colors
BTN_RUN_COLOR = "#4CAF50"         # Run calculation button
BTN_HYB_COLOR = "#1565C0"         # Hybridization analysis button

# Decomposed orbital palette (16 colors for multi-orbital line plots)
DECOMP_COLORS: list[str] = [
    "#E91E63", "#FF5722", "#FF9800", "#FFC107", "#CDDC39",
    "#4CAF50", "#009688", "#00BCD4", "#2196F3", "#3F51B5",
    "#673AB7", "#9C27B0", "#F44336", "#795548", "#607D8B", "#9E9E9E",
]

# Bar chart colors
BAR_COLORS = ["#2196F3", "#FF9800", "#4CAF50", "#E91E63", "#9C27B0"]

# Results table cell background colors (grouped by column zone)
TABLE_HEADER_BG = "#FFFFFF"
TABLE_BG_META = ["#FFFFFF", "#F8FAFC"]        # Label & Range (even, odd)
TABLE_BG_BASIC = ["#FFFFFF", "#F8FAFC"]       # Basic Properties
TABLE_BG_WEIGHTS = ["#FFFFFF", "#F8FAFC"]     # Orbital Weights
TABLE_BG_CENTERS = ["#FFFFFF", "#F8FAFC"]     # Orbital Centers

TABLE_HEADER_BG_DARK = "#2B2B2B"
TABLE_BG_META_DARK = ["transparent", "#2A2A2A"]
TABLE_BG_BASIC_DARK = ["#1A252C", "#1E2A38"]
TABLE_BG_WEIGHTS_DARK = ["#33251A", "#3D2B1E"]
TABLE_BG_CENTERS_DARK = ["#261A2A", "#301E36"]


# ── Chart annotation helper ──────────────────────────────────────────
# Moved from core/calculator.py to separate pure-numerical computation
# from matplotlib visualization concerns.

def annotate_center(
    ax,
    center: float,
    tag: str,
    color: str,
    lw: float,
    fontsize: float,
    y_offset_idx: int = 0,
) -> int:
    """Draw a vertical dashed line at the band center and annotate its value.

    Uses a blended coordinate system (X=Data, Y=Axes) to ensure the text
    is always positioned at 85% of the height, avoiding jumping when
    zooming or clipping. If the center is outside the x-axis limits,
    the line is omitted and the value is shown at the top-left corner.
    """
    if not np.isfinite(center):
        return y_offset_idx

    xlim = ax.get_xlim()
    if center < xlim[0] or center > xlim[1]:
        trans = ax.transAxes
        y_pos = 0.95 - (y_offset_idx * 0.12)
        ax.text(0.02, y_pos,
                f"{tag} = {center:.4f} eV",
                color=color, fontsize=fontsize, fontweight="bold",
                va="top", ha="left", clip_on=False, transform=trans,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))
        return y_offset_idx + 1

    ax.axvline(center, color=color, ls="-.", lw=lw, zorder=5)

    trans = mtransforms.blended_transform_factory(ax.transData, ax.transAxes)

    x_span = xlim[1] - xlim[0]
    offset = max(0.008 * x_span, 0.02)

    if center < xlim[0] + 0.3 * x_span:
        ha = "left"
        x_text = center + offset
    else:
        ha = "right"
        x_text = center - offset

    # ``y_offset_idx`` is used when an axes has more than one center (for
    # example, the two fragments in a hybridization overlap plot).  The old
    # implementation accepted the value but ignored it for in-range centers,
    # so nearby labels were drawn directly on top of each other.
    y_pos = max(0.08, 0.88 - (y_offset_idx * 0.16))
    ax.text(x_text, y_pos,
            f"{tag} = {center:.4f} eV",
            color=color, fontsize=fontsize, fontweight="bold",
            va="top", ha=ha, clip_on=True, transform=trans,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))

    return y_offset_idx + 1
