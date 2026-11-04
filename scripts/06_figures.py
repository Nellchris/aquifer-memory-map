"""Poster figures 1-5. Each saves a 300 dpi PDF and PNG into figures/.

Run after 05_analyse_recovery.py, 05a_sensitivity.py and 05b_survival.py.
"""

import collections
import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fig_style as S  # noqa: E402
from survival import km, observation_times  # noqa: E402

DATA = S.DATA
METHOD_STATION = "06374X0041/S"  # karstic, full coverage, -1.53 m dip, 11 mo


# ----------------------------------------------------------------- loaders
def load_recovery():
    rows = list(csv.DictReader((DATA / "recovery.csv").open(encoding="utf-8")))
    for r in rows:
        r["censored"] = r["censored"] == "True"
        r["months"] = None if r["censored"] else int(r["recovery_months"])
    return rows


def load_coords():
    coords = {}
    for r in csv.DictReader((DATA / "stations_classified.csv").open(encoding="utf-8")):
        try:
            coords[r["code_bss"]] = (float(r["x"]), float(r["y"]))
        except (TypeError, ValueError):
            continue
    return coords


def load_monthly(code=None):
    out = collections.defaultdict(dict)
    for r in csv.DictReader((DATA / "monthly_levels.csv").open(encoding="utf-8")):
        if code is None or r["code_bss"] == code:
            out[r["code_bss"]][r["year_month"]] = float(r["median_level"])
    return out


def load_normals(code=None):
    out = collections.defaultdict(dict)
    for r in csv.DictReader((DATA / "normals.csv").open(encoding="utf-8")):
        if code is None or r["code_bss"] == code:
            out[r["code_bss"]][int(r["month"])] = (
                float(r["median_normal"]), float(r["p25"]), float(r["p75"]))
    return out


def month_index(ym):
    y, m = ym.split("-")
    return int(y) * 12 + int(m) - 1


# ----------------------------------------------------------------- figure 1
def fig1_map():
    import geopandas as gpd
    from shapely.geometry import Point

    rec = load_recovery()
    coords = load_coords()

    france = gpd.read_file(DATA / "boundary" / "metropole.geojson").to_crs(2154)

    pts, months, cens_pts = [], [], []
    for r in rec:
        xy = coords.get(r["code_bss"])
        if not xy:
            continue
        if r["censored"]:
            cens_pts.append(Point(xy))
        else:
            pts.append(Point(xy))
            months.append(r["months"])

    recovered = gpd.GeoDataFrame({"months": months}, geometry=pts, crs=4326).to_crs(2154)
    censored = gpd.GeoDataFrame(geometry=cens_pts, crs=4326).to_crs(2154)

    fig, ax = plt.subplots(figsize=(8.4, 8.8))
    france.plot(ax=ax, facecolor="#f4f3ef", edgecolor="#b9b7ae", linewidth=0.8, zorder=1)

    censored.plot(ax=ax, color=S.CENSORED_GREY, markersize=13, marker="x",
                  linewidth=0.9, zorder=2, label="Not recovered by Dec 2025")
    sc = ax.scatter(recovered.geometry.x, recovered.geometry.y,
                    c=recovered["months"], cmap=S.sequential_cmap(), vmin=0, vmax=36,
                    s=20, linewidths=0.35, edgecolors="white", zorder=3)

    cbar = fig.colorbar(sc, ax=ax, shrink=0.46, pad=0.015, aspect=18)
    cbar.set_label("Months to recovery", color=S.INK)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(labelsize=10.5, color=S.GRID)

    ax.set_title("Groundwater recovery from the 2022 drought",
                 loc="left", color=S.INK, pad=12, fontsize=14)
    ax.text(0, 1.012, "{} metropolitan piezometers · months until the water table "
            "returned to its 2000-2019 monthly normal".format(len(rec)),
            transform=ax.transAxes, fontsize=10.5, color=S.INK_SECONDARY)

    # Scale bar: 200 km in Lambert-93, where map units are metres.
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    bx, by = x0 + 0.06 * (x1 - x0), y0 + 0.07 * (y1 - y0)
    ax.add_patch(Rectangle((bx, by), 200_000, 0.008 * (y1 - y0),
                           facecolor=S.INK, edgecolor="none", zorder=4))
    ax.text(bx + 100_000, by + 0.022 * (y1 - y0), "200 km", ha="center",
            fontsize=10.5, color=S.INK)

    nx, ny = x1 - 0.09 * (x1 - x0), y1 - 0.17 * (y1 - y0)
    ax.annotate("N", xy=(nx, ny), xytext=(nx, ny - 0.07 * (y1 - y0)),
                ha="center", fontsize=11.5, color=S.INK,
                arrowprops=dict(arrowstyle="-|>", color=S.INK, linewidth=1.4))

    ax.legend(loc="upper left", frameon=False, fontsize=10.5,
              bbox_to_anchor=(0.0, 0.92))
    ax.set_axis_off()
    ax.set_aspect("equal")
    return S.save(fig, "fig1_map_recovery")


# ----------------------------------------------------------------- figure 2
def fig2_depth_matched():
    sens = json.loads((DATA / "sensitivity.json").read_text(encoding="utf-8"))
    bands = [r for r in sens if r["label"].startswith("depth band")]
    titles = ["Shallow\n0.1-0.5 m below normal",
              "Moderate\n0.5-1.0 m below normal",
              "Deep\n1.0-3.0 m below normal"]

    fig, axes = plt.subplots(1, 3, figsize=(11.6, 5.0), sharey=True)
    for ax, band, title in zip(axes, bands, titles):
        for i, g in enumerate(S.GROUPS):
            e = band["groups"][g]
            if e["median"] is None:
                continue
            colour = S.MEDIUM_COLOR[g]
            ax.plot([e["q1"], e["q3"]], [i, i], color=colour, linewidth=3.0,
                    solid_capstyle="round", alpha=0.45, zorder=2)
            ax.plot([e["median"]], [i], marker=S.MEDIUM_MARKER[g], markersize=12,
                    color=colour, markeredgecolor="white", markeredgewidth=1.4,
                    zorder=3)
            # Direct label: identity and value never rely on colour alone.
            ax.text(e["median"], i - 0.3, "{:.0f} mo".format(e["median"]),
                    ha="center", va="top", fontsize=10.5, color=S.INK)
            ax.text(21.5, i, "n={}".format(e["n"]), ha="right", va="center",
                    fontsize=10, color=S.INK_MUTED)

        ax.set_yticks(range(len(S.GROUPS)))
        ax.set_yticklabels([S.MEDIUM_LABEL[g] for g in S.GROUPS])
        ax.set_xlim(0, 22)
        ax.set_ylim(-0.75, len(S.GROUPS) - 0.25)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=11.5, color=S.INK, pad=10)
        ax.set_xlabel("Months to recovery")
        ax.grid(axis="x", linewidth=0.6)
        ax.grid(axis="y", visible=False)

    # Mark the reversal in the deepest band.
    deep = bands[2]["groups"]
    axes[2].annotate(
        "ranking reverses:\nporous now slowest",
        xy=(deep["porous"]["median"], 0.22), xytext=(2.0, 1.30),
        fontsize=10.5, color=S.INK, ha="left", va="center",
        arrowprops=dict(arrowstyle="-|>", color=S.INK, linewidth=1.2,
                        shrinkB=10, connectionstyle="arc3,rad=-0.3"))

    fig.suptitle("Recovery time depends on how far the water table fell",
                 x=0.011, ha="left", fontsize=14, color=S.INK, y=1.02)
    fig.text(0.011, 0.955, "Median months to recovery with interquartile range, "
             "stations matched on drought severity. Fissured is fastest in every "
             "band.", fontsize=10.5, color=S.INK_SECONDARY, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return S.save(fig, "fig2_depth_matched")


# ----------------------------------------------------------------- figure 3
def fig3_kaplan_meier():
    rec = load_recovery()
    surv = json.loads((DATA / "survival_summary.json").read_text(encoding="utf-8"))
    last_month = {}
    for r in csv.DictReader((DATA / "monthly_levels.csv").open(encoding="utf-8")):
        cb, ym = r["code_bss"], r["year_month"]
        if cb not in last_month or ym > last_month[cb]:
            last_month[cb] = ym

    fig, ax = plt.subplots(figsize=(8.6, 5.8))
    handles = []
    for g in S.GROUPS:
        sub = [r for r in rec if r["aquifer_medium"] == g]
        times, events = observation_times(sub, last_month)
        curve = km(times, events)

        xs, ys = [0.0], [1.0]
        for t, s, *_ in curve:
            xs.extend([t, t])
            ys.extend([ys[-1], s])
        colour = S.MEDIUM_COLOR[g]
        ax.step(xs, ys, where="post", color=colour, linewidth=2.2, zorder=3)

        # Censoring ticks: one per censored station, at its censoring time.
        cens_t = [t for t, _s, _n, _d, c in curve if c > 0]
        cens_y = [s for t, s, _n, _d, c in curve if c > 0]
        ax.plot(cens_t, cens_y, linestyle="none", marker="|", markersize=9,
                color=colour, markeredgewidth=1.6, zorder=4)

        e = surv["groups"][g]
        med = e["km_median_months"]
        if med is not None:
            ax.plot([med], [0.5], marker=S.MEDIUM_MARKER[g], markersize=10,
                    color=colour, markeredgecolor="white", markeredgewidth=1.3,
                    zorder=5)
        label = "{}  (n={}, median {:.0f} mo)".format(
            S.MEDIUM_LABEL[g], e["n"], med)
        handles.append(Line2D([], [], color=colour, linewidth=2.2,
                              marker=S.MEDIUM_MARKER[g], markersize=8,
                              markeredgecolor="white", label=label))

    ax.axhline(0.5, color=S.INK_MUTED, linewidth=0.9, linestyle=(0, (4, 4)), zorder=1)
    ax.text(41.4, 0.515, "median", fontsize=10, color=S.INK_MUTED)

    lr = surv["logrank_bonferroni"]
    lines = ["Log-rank, Bonferroni:"] + [
        "  {}  p = {:.1e}".format(k.replace(" vs ", " vs "), v["p_bonferroni"])
        for k, v in lr.items()]
    ax.text(0.985, 0.955, "\n".join(lines), transform=ax.transAxes,
            ha="right", va="top", fontsize=10, color=S.INK_SECONDARY,
            linespacing=1.5)

    ax.set_xlim(0, 42)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Months since drought minimum")
    ax.set_ylabel("Proportion not yet recovered")
    S.titled(ax, "Fissured aquifers recover first; karstic last",
             "Kaplan-Meier estimate. Vertical ticks mark censored stations, "
             "still unrecovered when observation ends.")
    S.legend_with_labels(ax, handles, [h.get_label() for h in handles],
                         loc="upper right", frameon=False,
                         bbox_to_anchor=(1.0, 0.70))
    ax.grid(axis="both", linewidth=0.6)
    return S.save(fig, "fig3_kaplan_meier")


# ----------------------------------------------------------------- figure 4
def fig4_boxplot():
    rec = load_recovery()
    stats_summary = json.loads((DATA / "stats_summary.json").read_text(encoding="utf-8"))
    dunn = stats_summary["primary"]["dunn_bonferroni"] or {}

    values = {g: [r["months"] for r in rec
                  if r["aquifer_medium"] == g and not r["censored"]]
              for g in S.GROUPS}

    fig, ax = plt.subplots(figsize=(8.0, 6.2))
    rng = np.random.default_rng(20220601)

    for i, g in enumerate(S.GROUPS):
        v = np.array(values[g], dtype=float)
        colour = S.MEDIUM_COLOR[g]
        bp = ax.boxplot([v], positions=[i], widths=0.46, showfliers=False,
                        patch_artist=True, zorder=3,
                        medianprops=dict(color=S.INK, linewidth=2.0),
                        whiskerprops=dict(color=colour, linewidth=1.4),
                        capprops=dict(color=colour, linewidth=1.4))
        for box in bp["boxes"]:
            box.set(facecolor=colour, alpha=0.26, edgecolor=colour, linewidth=1.5)

        jitter = rng.normal(0, 0.055, size=v.size)
        ax.plot(i + jitter, v, linestyle="none", marker=S.MEDIUM_MARKER[g],
                markersize=3.4, color=colour, alpha=0.5, zorder=2)

        e = stats_summary["primary"]["groups"][g]
        ax.text(i, -2.4, "n = {}\n{} censored".format(e["n"], e["n_censored"]),
                ha="center", va="top", fontsize=10, color=S.INK_SECONDARY)
        ax.text(i + 0.30, np.median(v), "{:.0f} mo".format(np.median(v)),
                ha="left", va="center", fontsize=11, color=S.INK, zorder=6,
                bbox=dict(facecolor=S.SURFACE, edgecolor="none",
                          boxstyle="round,pad=0.18", alpha=0.85))

    # Significance brackets from Dunn's, Bonferroni-adjusted.
    def stars(p):
        return "ns" if p >= 0.05 else "*" if p >= 0.01 else "**" if p >= 0.001 else "***"

    brackets = [("porous vs fissured", 0, 1, 41), ("fissured vs karstic", 1, 2, 47),
                ("porous vs karstic", 0, 2, 53)]
    for key, a, b, y in brackets:
        if key not in dunn:
            continue
        p = dunn[key]["p_bonferroni"]
        ax.plot([a, a, b, b], [y, y + 1.4, y + 1.4, y], color=S.INK_SECONDARY,
                linewidth=1.1, zorder=4)
        ax.text((a + b) / 2, y + 2.0,
                "{}  p = {:.3f}".format(stars(p), p) if p >= 0.001
                else "{}  p = {:.0e}".format(stars(p), p),
                ha="center", fontsize=10, color=S.INK)

    ax.set_xticks(range(len(S.GROUPS)))
    ax.set_xticklabels([S.MEDIUM_LABEL[g] for g in S.GROUPS])
    ax.set_ylim(-9, 60)
    ax.set_ylabel("Months to recovery")
    S.titled(ax, "Recovery time by aquifer medium",
             "Uncensored stations only; censored counts beneath each box. "
             "Dunn's post-hoc, Bonferroni-adjusted.")
    ax.grid(axis="y", linewidth=0.6)
    ax.grid(axis="x", visible=False)
    return S.save(fig, "fig4_boxplot")


# ----------------------------------------------------------------- figure 5
def fig5_method_inset():
    code = METHOD_STATION
    monthly = load_monthly(code)[code]
    normals = load_normals(code)[code]
    rec = {r["code_bss"]: r for r in load_recovery()}[code]
    dmin = {r["code_bss"]: r for r in
            csv.DictReader((DATA / "drought_min.csv").open(encoding="utf-8"))}[code]

    lo, hi = "2019-01", "2026-06"
    months = sorted(ym for ym in monthly if lo <= ym <= hi)
    xs = [month_index(ym) for ym in months]
    ys = [monthly[ym] for ym in months]
    med = [normals[int(ym.split("-")[1])][0] for ym in months]
    p25 = [normals[int(ym.split("-")[1])][1] for ym in months]
    p75 = [normals[int(ym.split("-")[1])][2] for ym in months]

    fig, ax = plt.subplots(figsize=(10.4, 5.2))
    ax.fill_between(xs, p25, p75, color="#d9d7d0", zorder=1,
                    label="Normal band (25th-75th percentile, 2000-2019)")
    ax.plot(xs, med, color="#5f5e59", linewidth=1.6, linestyle=(0, (5, 3)),
            zorder=2, label="Monthly normal (median)")
    ax.plot(xs, ys, color="#111111", linewidth=2.0, zorder=3,
            label="Observed monthly level")

    min_x = month_index(dmin["min_date"])
    min_y = float(dmin["min_level"])
    rec_x = month_index(rec["recovery_date"])
    rec_y = monthly[rec["recovery_date"]]

    ax.plot([min_x], [min_y], marker="v", markersize=11, color="#111111",
            markeredgecolor="white", markeredgewidth=1.2, zorder=5)
    ax.plot([rec_x], [rec_y], marker="o", markersize=10, color="#111111",
            markeredgecolor="white", markeredgewidth=1.2, zorder=5)

    span = max(ys) - min(ys)
    ax.annotate("Drought minimum\n{}  ({:+.2f} m vs normal)".format(
                    dmin["min_date"], float(dmin["departure"])),
                xy=(min_x, min_y), xytext=(min_x - 30, min_y + 0.11 * span),
                fontsize=10.5, color=S.INK, ha="left",
                arrowprops=dict(arrowstyle="-|>", color=S.INK, linewidth=1.2,
                                shrinkB=9))
    ax.annotate("Recovery point\nfirst of 2 consecutive\nmonths at or above normal",
                xy=(rec_x, rec_y), xytext=(rec_x + 4, rec_y - 0.30 * span),
                fontsize=10.5, color=S.INK, ha="left",
                arrowprops=dict(arrowstyle="-|>", color=S.INK, linewidth=1.2))

    bar_y = min(ys) - 0.11 * span
    ax.annotate("", xy=(min_x, bar_y), xytext=(rec_x, bar_y),
                arrowprops=dict(arrowstyle="<|-|>", color="#111111", linewidth=1.3))
    ax.text((min_x + rec_x) / 2, bar_y - 0.03 * span,
            "Recovery time = {} months".format(rec["recovery_months"]),
            ha="center", va="top", fontsize=11.5, color=S.INK)

    ticks = [month_index("{}-01".format(y)) for y in range(2019, 2027)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(y) for y in range(2019, 2027)])
    ax.set_xlim(min(xs) - 1, max(xs) + 1)
    ax.set_ylim(bar_y - 0.17 * span,
                max(max(ys), max(p75)) + 0.30 * span)
    ax.set_ylabel("Water-table elevation (m NGF)")
    S.titled(ax, "How recovery time is measured",
             "Station {} (karstic), one of {} analysed".format(
                 code, len(load_recovery())))
    ax.legend(loc="upper left", frameon=True, fontsize=10.5, framealpha=0.92,
              edgecolor="none", facecolor=S.SURFACE, ncol=1,
              borderpad=0.7, handlelength=2.4)
    ax.grid(axis="y", linewidth=0.6)
    ax.grid(axis="x", visible=False)
    return S.save(fig, "fig5_method_inset")


def main():
    S.apply_style()
    written = []
    for fn in (fig1_map, fig2_depth_matched, fig3_kaplan_meier,
               fig4_boxplot, fig5_method_inset):
        paths = fn()
        written.extend(paths)
        print("  {:<34} {}".format(fn.__name__, ", ".join(p.name for p in paths)))
    return written


if __name__ == "__main__":
    main()
