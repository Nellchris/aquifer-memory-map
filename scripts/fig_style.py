"""Shared figure style, palette and save helper.

Palette: the three medium colours are categorical slots 1-3 of the data-viz
reference palette, which is the only subset that clears the all-pairs
colourblind floors (worst pair CVD dE 9.2, normal-vision dE 24.0). Assigned in
fixed order and never cycled, so a medium keeps its colour across all figures.

Slot 3 (aqua, karstic) sits below 3:1 contrast on a white surface, so the
relief rule applies: every figure using it ships visible direct labels, not
colour alone. Each figure also varies marker shape by medium, giving a second,
non-colour channel for print and photocopies.

Recovery time is a MAGNITUDE, not a polarity, so the map uses a single-hue
sequential ramp rather than the diverging scale the brief suggested; there is no
meaningful midpoint for "months to recover" to diverge about.
"""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIGURES = ROOT / "figures"

GROUPS = ("porous", "fissured", "karstic")

# Categorical slots 1, 2, 3 — fixed order, never cycled.
MEDIUM_COLOR = {
    "porous": "#2a78d6",    # slot 1, blue
    "fissured": "#eb6834",  # slot 2, orange
    "karstic": "#1baf7a",   # slot 3, aqua
}
# Second, non-colour channel for identity (print, CVD, photocopy).
MEDIUM_MARKER = {"porous": "o", "fissured": "s", "karstic": "^"}
MEDIUM_HATCH = {"porous": "...", "fissured": "///", "karstic": "xxx"}
MEDIUM_LABEL = {"porous": "Porous", "fissured": "Fissured", "karstic": "Karstic"}

# Sequential ramp for recovery months (magnitude), plus a reserved grey for
# "never recovered", which is a state and not a value on the ramp.
SEQUENTIAL = "viridis_r"
CENSORED_GREY = "#9a9a97"

SURFACE = "#ffffff"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#86857f"
GRID = "#dedcd5"


def apply_style():
    plt.style.use("seaborn-v0_8-whitegrid")
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        # Sized so nothing falls below 10pt when printed at the saved size.
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11.5,
        "xtick.labelsize": 10.5,
        "ytick.labelsize": 10.5,
        "legend.fontsize": 10.5,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": INK_SECONDARY,
        "ytick.color": INK_SECONDARY,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 2.0,
        "patch.linewidth": 0.0,
        "legend.frameon": False,
        "pdf.fonttype": 42,   # embed as TrueType so text stays editable
        "svg.fonttype": "none",
    })


def save(fig, stem, svg=False):
    """Write <stem>.pdf and .png at 300 dpi, optionally .svg. Returns paths."""
    FIGURES.mkdir(exist_ok=True)
    written = []
    for ext in (["pdf", "png", "svg"] if svg else ["pdf", "png"]):
        path = FIGURES / "{}.{}".format(stem, ext)
        fig.savefig(path, dpi=300, bbox_inches="tight", facecolor=SURFACE)
        written.append(path)
    plt.close(fig)
    return written


def legend_with_labels(ax, handles, labels, **kw):
    """Legend present for every multi-series figure (identity never colour-alone)."""
    leg = ax.legend(handles, labels, **kw)
    for text in leg.get_texts():
        text.set_color(INK)
    return leg


def titled(ax, title, subtitle=None):
    """Title above subtitle above the axes, with no overlap.

    set_title plus a text at y~1.01 collides whenever the axes has visible
    ticks, so both lines are placed explicitly in axes coordinates.
    """
    y = 1.105 if subtitle else 1.04
    ax.text(0, y, title, transform=ax.transAxes, fontsize=14,
            color=INK, ha="left", va="bottom")
    if subtitle:
        ax.text(0, 1.028, subtitle, transform=ax.transAxes, fontsize=10.5,
                color=INK_SECONDARY, ha="left", va="bottom")


def sequential_cmap(low=0.12, high=1.0):
    """viridis_r with the palest end trimmed, so low values stay visible
    against a light map surface."""
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    base = plt.get_cmap(SEQUENTIAL)
    return LinearSegmentedColormap.from_list(
        "recovery", base(np.linspace(low, high, 256)))

