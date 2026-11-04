"""Figure 6: conceptual cross-section of the three aquifer media.

Schematic, not data-driven. Drawn with matplotlib so it exports SVG, PDF and
PNG from one source with no external rasteriser, and with the same fonts and
colours as the data figures. (An SVG-by-hand version needed cairosvg/rsvg,
neither of which is present on this machine.)

Each block carries its medium colour AND a distinct hatch, so the three read
apart in greyscale and for colourblind viewers.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse, FancyArrow, FancyArrowPatch, Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fig_style as S  # noqa: E402

PANELS = [
    {
        "key": "porous",
        "title": "Porous",
        "porosity": "Intergranular pore space",
        "water_table": 0.62,
        "flow_len": 0.16,
        "flow": "Slow, diffuse seepage\nthrough the matrix",
        "trans": "Low transmissivity\nHigh storage",
    },
    {
        "key": "fissured",
        "title": "Fissured",
        "porosity": "Connected fracture network",
        "water_table": 0.70,
        "flow_len": 0.32,
        "flow": "Moderate flow along\nfractures",
        "trans": "Moderate transmissivity\nLow storage",
    },
    {
        "key": "karstic",
        "title": "Karstic",
        "porosity": "Dissolution conduits and caves",
        "water_table": 0.50,
        "flow_len": 0.56,
        "flow": "Rapid conduit flow,\nflashy response",
        "trans": "Very high transmissivity\nVery low storage",
    },
]


def draw_texture(ax, key, colour, rng, clip):
    """The medium's internal structure, drawn rather than hatched.

    Everything is clipped to the block, or fractures and conduits spill past
    its edges.
    """
    artists = []
    if key == "porous":
        xs = rng.uniform(0.04, 0.96, 230)
        ys = rng.uniform(0.04, 0.96, 230)
        artists.append(ax.scatter(xs, ys, s=rng.uniform(5, 26, 230),
                                  color=colour, alpha=0.45, linewidths=0,
                                  zorder=3))

    elif key == "fissured":
        for _ in range(26):
            x0, y0 = rng.uniform(0.02, 0.98), rng.uniform(0.02, 0.98)
            pts = [(x0, y0)]
            for _ in range(3):
                x0 += rng.uniform(-0.16, 0.16)
                y0 += rng.uniform(-0.18, 0.18)
                pts.append((x0, y0))
            xs, ys = zip(*pts)
            artists.extend(ax.plot(xs, ys, color=colour,
                                   linewidth=rng.uniform(0.9, 2.1), alpha=0.6,
                                   solid_capstyle="round", zorder=3))

    else:  # karstic
        centres = [(0.20, 0.72), (0.47, 0.58), (0.74, 0.70),
                   (0.33, 0.30), (0.63, 0.26), (0.86, 0.42)]
        for cx, cy in centres:
            artists.append(ax.add_patch(Ellipse(
                (cx, cy), rng.uniform(0.15, 0.24), rng.uniform(0.07, 0.11),
                angle=rng.uniform(-18, 18), facecolor=colour, alpha=0.40,
                zorder=3)))
        chain = sorted(centres, key=lambda c: c[0])
        for (x0, y0), (x1, y1) in zip(chain, chain[1:]):
            artists.append(ax.add_patch(FancyArrowPatch(
                (x0, y0), (x1, y1), arrowstyle="-", linewidth=3.0,
                color=colour, alpha=0.45, zorder=3,
                connectionstyle="arc3,rad=0.12")))

    for a in artists:
        a.set_clip_path(clip)


def panel(ax, spec, rng):
    key = spec["key"]
    colour = S.MEDIUM_COLOR[key]
    wt = spec["water_table"]

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.78, 1.58)
    ax.set_axis_off()

    ax.text(0, 1.50, spec["title"], fontsize=17, color=S.INK,
            fontweight="bold", va="bottom")
    ax.text(0, 1.40, spec["porosity"], fontsize=11, color=S.INK_SECONDARY,
            va="bottom")

    # Recharge arrows above the ground surface.
    for x in np.linspace(0.10, 0.90, 5):
        ax.add_patch(FancyArrow(x, 1.19, 0, -0.13, width=0.004,
                                head_width=0.035, head_length=0.05,
                                color=S.INK_SECONDARY, alpha=0.8, zorder=4))
    ax.text(0.0, 1.235, "Recharge", fontsize=10.5, color=S.INK_MUTED,
            va="bottom")

    # The block: unsaturated above the water table, saturated below.
    block = ax.add_patch(Rectangle((0, 0), 1, 1, facecolor="#f6f5f1",
                                   edgecolor="#c6c4bc", linewidth=1.3, zorder=1))
    ax.add_patch(Rectangle((0, 0), 1, wt, facecolor=colour, alpha=0.15,
                           edgecolor="none", zorder=2))
    draw_texture(ax, key, colour, rng, block)

    # Water table.
    ax.plot([0.01, 0.99], [wt, wt], color=colour, linewidth=3.0,
            solid_capstyle="round", zorder=5)
    ax.plot([0.07], [wt], marker="v", markersize=10, color=colour,
            markeredgecolor="white", markeredgewidth=1.1, zorder=6)
    ax.text(0.99, wt + 0.045, "water table", fontsize=10.5, ha="right",
            color=S.INK_SECONDARY, zorder=7,
            bbox=dict(facecolor=S.SURFACE, edgecolor="none",
                      boxstyle="round,pad=0.15", alpha=0.85))

    # Lateral flow: arrow length encodes relative transmissivity.
    fy = wt - 0.26
    ax.add_patch(FancyArrow(0.08, fy, spec["flow_len"], 0, width=0.012,
                            head_width=0.055, head_length=0.055,
                            color=colour, zorder=6, length_includes_head=True))
    ax.text(0.08, fy + 0.07, "flow", fontsize=10.5, color=S.INK_SECONDARY, zorder=6)

    ax.text(0, -0.10, spec["flow"], fontsize=11.5, color=S.INK,
            va="top", linespacing=1.5)
    ax.text(0, -0.45, spec["trans"], fontsize=11, color=S.INK_SECONDARY,
            va="top", linespacing=1.5)


def main():
    S.apply_style()
    rng = np.random.default_rng(20220601)

    fig, axes = plt.subplots(1, 3, figsize=(12.6, 5.4))
    for ax, spec in zip(axes, PANELS):
        panel(ax, spec, rng)

    fig.suptitle("Three aquifer media, three ways water moves",
                 x=0.012, ha="left", fontsize=16, color=S.INK, y=1.14)
    fig.text(0.012, 1.065,
             "Schematic. Arrow length indicates relative transmissivity; "
             "storage runs the opposite way.",
             fontsize=11, color=S.INK_SECONDARY, ha="left")
    fig.subplots_adjust(wspace=0.22)

    paths = S.save(fig, "fig6_cross_section", svg=True)
    for p in paths:
        print("  wrote {}".format(p.name))


if __name__ == "__main__":
    main()
