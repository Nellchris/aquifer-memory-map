"""Cartographic maps: fig1 (upgraded), fig7 (aquifer medium), fig8 (severity).

Basemap: Natural Earth 1:10m shaded relief (SR_LR.tif), warped to Lambert-93
and clipped to metropolitan France.

Why not contextily: the brief suggested it first, but Stamen.Terrain is no
longer freely served (it moved to Stadia and needs an API key), and the
remaining free option, CartoDB Positron, is a street basemap rather than
terrain. Web tiles also arrive at a fixed zoom, so they soften badly when a
figure is printed at 300 dpi, and they carry attribution requirements. The
Natural Earth raster gives genuine terrain, prints predictably, and keeps the
pipeline reproducible offline once downloaded.

Its one limitation: at 1.33 arcmin, France is only ~540 px wide in the source,
so the relief is upsampled about 4x for print. That is acceptable for a muted
backdrop -- shaded relief is diffuse anyway -- and bilinear warping keeps it
smooth rather than blocky. It is not suitable for reading terrain detail.

All three maps share one projection (EPSG:2154), one basemap treatment, and the
palette and markers from fig_style, so they sit together on the poster.
"""

import csv
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from rasterio import features
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fig_style as S  # noqa: E402

DATA = S.DATA
RELIEF = DATA / "basemap" / "SR_LR.tif"
METROPOLE = DATA / "boundary" / "metropole.geojson"
DEPARTEMENTS = DATA / "boundary" / "departements.geojson"

CRS = 2154                 # Lambert-93
TARGET_WIDTH_PX = 2600     # warp resolution, sized for a 300 dpi print
RELIEF_ALPHA = 0.80        # muted: the stations are the subject, not the terrain

CITIES = [
    ("Paris", 2.3522, 48.8566, "left", "bottom"),
    ("Lyon", 4.8357, 45.7640, "left", "bottom"),
    ("Marseille", 5.3698, 43.2965, "left", "top"),
    ("Bordeaux", -0.5792, 44.8378, "right", "bottom"),
    ("Strasbourg", 7.7521, 48.5734, "right", "bottom"),
]

# Muted warm-grey ramp for the relief, so it never competes with the data.
RELIEF_CMAP = LinearSegmentedColormap.from_list(
    "relief", ["#6f6c62", "#a8a59a", "#d2cfc4", "#eeece4", "#faf9f5"])

# Sequential reds for drought severity (magnitude below normal).
SEVERITY_CMAP = "YlOrRd"
SEVERITY_MAX = 2.5  # metres below normal; deeper is clipped to the top colour


# ------------------------------------------------------------------ basemap
def load_boundaries():
    france = gpd.read_file(METROPOLE).to_crs(CRS)
    depts = gpd.read_file(DEPARTEMENTS).to_crs(CRS)
    return france, depts


def warp_relief(france):
    """Shaded relief warped to Lambert-93 and masked to France.

    Returns (array with NaN outside France, extent for imshow).
    """
    minx, miny, maxx, maxy = france.total_bounds
    pad = 20_000
    minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad

    height = int(TARGET_WIDTH_PX * (maxy - miny) / (maxx - minx))
    dst_transform = rasterio.transform.from_bounds(
        minx, miny, maxx, maxy, TARGET_WIDTH_PX, height)
    dst = np.zeros((height, TARGET_WIDTH_PX), dtype=np.float32)

    with rasterio.open(RELIEF) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=rasterio.crs.CRS.from_epsg(CRS),
            resampling=Resampling.bilinear,
        )

    inside = features.geometry_mask(
        france.geometry, out_shape=dst.shape, transform=dst_transform,
        invert=True, all_touched=True)
    dst[~inside] = np.nan
    return dst, (minx, maxx, miny, maxy)


def base_map(ax, france, depts, relief, extent, cities=True):
    """Relief, boundaries, cities. Shared by all three maps."""
    ax.imshow(relief, extent=extent, origin="upper", cmap=RELIEF_CMAP,
              alpha=RELIEF_ALPHA, interpolation="bilinear", zorder=1)

    depts.boundary.plot(ax=ax, color="#b0ada3", linewidth=0.35, zorder=2)
    france.boundary.plot(ax=ax, color="#7d7a71", linewidth=1.0, zorder=3)

    if cities:
        pts = gpd.GeoDataFrame(
            geometry=[Point(lon, lat) for _n, lon, lat, _h, _v in CITIES],
            crs=4326).to_crs(CRS)
        for (name, _lon, _lat, ha, va), geom in zip(CITIES, pts.geometry):
            ax.plot([geom.x], [geom.y], marker="o", markersize=4.5,
                    color="#3a3833", markeredgecolor="white",
                    markeredgewidth=0.8, zorder=9)
            dx = 11_000 if ha == "left" else -11_000
            dy = 7_000 if va == "bottom" else -7_000
            ax.text(geom.x + dx, geom.y + dy, name, fontsize=9.5, ha=ha,
                    va=va, color="#3a3833", zorder=9,
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.65,
                              boxstyle="round,pad=0.12"))

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_axis_off()


def scale_bar_and_north(ax, km=200):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    bx, by = x0 + 0.05 * (x1 - x0), y0 + 0.06 * (y1 - y0)
    ax.add_patch(Rectangle((bx, by), km * 1000, 0.007 * (y1 - y0),
                           facecolor=S.INK, edgecolor="none", zorder=10))
    ax.text(bx + km * 500, by + 0.019 * (y1 - y0), "{} km".format(km),
            ha="center", fontsize=9.5, color=S.INK, zorder=10)

    nx, ny = x1 - 0.055 * (x1 - x0), y1 - 0.20 * (y1 - y0)
    ax.annotate("N", xy=(nx, ny), xytext=(nx, ny - 0.065 * (y1 - y0)),
                ha="center", fontsize=11, color=S.INK, zorder=10,
                arrowprops=dict(arrowstyle="-|>", color=S.INK, linewidth=1.3))


def map_title(fig, ax, title, subtitle):
    ax.text(0, 1.055, title, transform=ax.transAxes, fontsize=14.5,
            color=S.INK, ha="left", va="bottom")
    ax.text(0, 1.012, subtitle, transform=ax.transAxes, fontsize=10.5,
            color=S.INK_SECONDARY, ha="left", va="bottom")


# --------------------------------------------------------------------- data
def load_points():
    """One record per analysed station: coords, medium, recovery, departure."""
    coords = {}
    for r in csv.DictReader((DATA / "stations_classified.csv").open(encoding="utf-8")):
        try:
            coords[r["code_bss"]] = (float(r["x"]), float(r["y"]))
        except (TypeError, ValueError):
            continue

    departure = {
        r["code_bss"]: float(r["departure"])
        for r in csv.DictReader((DATA / "drought_min.csv").open(encoding="utf-8"))
    }

    rows = []
    for r in csv.DictReader((DATA / "recovery.csv").open(encoding="utf-8")):
        xy = coords.get(r["code_bss"])
        if not xy:
            continue
        censored = r["censored"] == "True"
        rows.append({
            "code_bss": r["code_bss"],
            "lon": xy[0], "lat": xy[1],
            "medium": r["aquifer_medium"],
            "censored": censored,
            "months": None if censored else int(r["recovery_months"]),
            "departure": departure.get(r["code_bss"]),
        })
    return rows


def to_gdf(rows):
    return gpd.GeoDataFrame(
        {k: [r[k] for r in rows] for k in rows[0] if k not in ("lon", "lat")},
        geometry=[Point(r["lon"], r["lat"]) for r in rows],
        crs=4326).to_crs(CRS)


# ------------------------------------------------------------------- fig  1
def fig1(ctx, rows):
    france, depts, relief, extent = ctx
    fig, ax = plt.subplots(figsize=(8.6, 9.0))
    base_map(ax, france, depts, relief, extent)

    gdf = to_gdf(rows)
    cens = gdf[gdf["censored"]]
    recov = gdf[~gdf["censored"]]

    ax.scatter(cens.geometry.x, cens.geometry.y, marker="x", s=17,
               c=S.CENSORED_GREY, linewidths=0.9, zorder=6,
               label="Not recovered (n={})".format(len(cens)))
    sc = ax.scatter(recov.geometry.x, recov.geometry.y, c=recov["months"],
                    cmap=S.sequential_cmap(), vmin=0, vmax=36, s=21,
                    linewidths=0.35, edgecolors="white", zorder=7)

    cbar = fig.colorbar(sc, ax=ax, shrink=0.42, pad=0.01, aspect=17)
    cbar.set_label("Months to recovery", color=S.INK, fontsize=10.5)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(labelsize=10, color=S.GRID)

    scale_bar_and_north(ax)
    ax.legend(loc="upper left", frameon=True, framealpha=0.85,
              edgecolor="none", facecolor="white", fontsize=10,
              bbox_to_anchor=(0.0, 1.0))
    map_title(fig, ax, "Groundwater recovery from the 2022 drought",
              "{} metropolitan piezometers - months until the water table "
              "returned to its 2000-2019 monthly normal".format(len(gdf)))
    return S.save(fig, "fig1_map_recovery")


# ------------------------------------------------------------------- fig  7
def fig7(ctx, rows):
    france, depts, relief, extent = ctx
    fig, ax = plt.subplots(figsize=(8.6, 9.0))
    base_map(ax, france, depts, relief, extent)

    gdf = to_gdf(rows)
    handles = []
    # Drawn rarest first so the sparse karstic points are not buried.
    for medium in ("porous", "fissured", "karstic"):
        sub = gdf[gdf["medium"] == medium]
        ax.scatter(sub.geometry.x, sub.geometry.y,
                   marker=S.MEDIUM_MARKER[medium], s=24,
                   c=S.MEDIUM_COLOR[medium], linewidths=0.4,
                   edgecolors="white",
                   zorder=6 + ("porous", "fissured", "karstic").index(medium))
        handles.append(Line2D([], [], linestyle="none",
                              marker=S.MEDIUM_MARKER[medium], markersize=8,
                              color=S.MEDIUM_COLOR[medium],
                              markeredgecolor="white", markeredgewidth=0.6,
                              label="{}  (n={})".format(
                                  S.MEDIUM_LABEL[medium], len(sub))))

    scale_bar_and_north(ax)
    S.legend_with_labels(ax, handles, [h.get_label() for h in handles],
                         loc="upper left", frameon=True, framealpha=0.85,
                         edgecolor="none", facecolor="white", fontsize=10.5,
                         bbox_to_anchor=(0.0, 0.97))
    map_title(fig, ax, "Station network by aquifer medium",
              "{} metropolitan piezometers classified via BDLISA v3".format(len(gdf)))
    return S.save(fig, "fig7_map_medium")


# ------------------------------------------------------------------- fig  8
def fig8(ctx, rows):
    france, depts, relief, extent = ctx
    fig, ax = plt.subplots(figsize=(8.6, 9.0))
    base_map(ax, france, depts, relief, extent)

    gdf = to_gdf(rows)
    gdf = gdf[gdf["departure"].notna()]
    # Plot the magnitude below normal; stations at or above normal are a
    # different thing from a shallow drought, so they get their own mark.
    below = gdf[gdf["departure"] < 0].copy()
    below["drop_m"] = below["departure"].abs()
    above = gdf[gdf["departure"] >= 0]

    ax.scatter(above.geometry.x, above.geometry.y, marker="o", s=15,
               facecolors="none", edgecolors="#9a9a97", linewidths=0.8,
               zorder=6, label="At or above normal (n={})".format(len(above)))
    sc = ax.scatter(below.geometry.x, below.geometry.y, c=below["drop_m"],
                    cmap=SEVERITY_CMAP, vmin=0, vmax=SEVERITY_MAX, s=22,
                    linewidths=0.35, edgecolors="white", zorder=7)

    cbar = fig.colorbar(sc, ax=ax, shrink=0.42, pad=0.01, aspect=17,
                        extend="max")
    cbar.set_label("Metres below normal at the drought minimum",
                   color=S.INK, fontsize=10.5)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(labelsize=10, color=S.GRID)

    scale_bar_and_north(ax)
    ax.legend(loc="upper left", frameon=True, framealpha=0.85,
              edgecolor="none", facecolor="white", fontsize=10,
              bbox_to_anchor=(0.0, 1.0))
    map_title(fig, ax, "Drought severity: departure from normal at minimum",
              "Deeper colour = water table fell further below its 2000-2019 "
              "monthly normal. Severity is the key confound.")
    return S.save(fig, "fig8_map_severity")


def main():
    S.apply_style()
    for path in (RELIEF, METROPOLE, DEPARTEMENTS):
        if not path.exists():
            sys.exit("missing {} - see the download steps in the README".format(path))

    france, depts = load_boundaries()
    print("warping shaded relief to EPSG:{} ...".format(CRS))
    relief, extent = warp_relief(france)
    print("  relief {} x {} px".format(relief.shape[1], relief.shape[0]))
    ctx = (france, depts, relief, extent)

    rows = load_points()
    print("{} analysed stations with coordinates".format(len(rows)))
    deps = [r["departure"] for r in rows if r["departure"] is not None]
    print("  departure range {:.2f} to {:.2f} m (ramp clipped at -{} m)".format(
        min(deps), max(deps), SEVERITY_MAX))
    below = sum(1 for d in deps if d < -SEVERITY_MAX)
    print("  {} stations fell deeper than the ramp maximum".format(below))

    for fn in (fig1, fig7, fig8):
        paths = fn(ctx, rows)
        print("  {:<6} {}".format(fn.__name__, ", ".join(p.name for p in paths)))


if __name__ == "__main__":
    main()
