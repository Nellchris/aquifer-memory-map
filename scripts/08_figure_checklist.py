"""Confirm every poster figure exists, in every required format, with sizes."""
import sys
from pathlib import Path

FIGURES = Path(__file__).resolve().parent.parent / "figures"

EXPECTED = [
    ("fig1_map_recovery", ["pdf", "png"], "Map of France, recovery time"),
    ("fig2_depth_matched", ["pdf", "png"], "Depth-matched recovery (key figure)"),
    ("fig3_kaplan_meier", ["pdf", "png"], "Kaplan-Meier survival curves"),
    ("fig4_boxplot", ["pdf", "png"], "Pooled box plot with strip"),
    ("fig5_method_inset", ["pdf", "png"], "Method inset hydrograph"),
    ("fig6_cross_section", ["pdf", "png", "svg"], "Conceptual cross-section"),
    ("fig7_map_medium", ["pdf", "png"], "Station network by aquifer medium"),
    ("fig8_map_severity", ["pdf", "png"], "Drought severity, departure from normal"),
]


def png_size(path):
    """Width, height and dpi straight from the PNG header chunks."""
    data = path.read_bytes()
    w = int.from_bytes(data[16:20], "big")
    h = int.from_bytes(data[20:24], "big")
    dpi = None
    idx = data.find(b"pHYs")
    if idx != -1:
        ppu_x = int.from_bytes(data[idx + 4:idx + 8], "big")
        if data[idx + 12] == 1:  # unit is metres
            dpi = round(ppu_x * 0.0254)
    return w, h, dpi


def main():
    print("FIGURE CHECKLIST")
    print("=" * 78)
    ok = True
    for stem, exts, desc in EXPECTED:
        print("\n{}  -- {}".format(stem, desc))
        for ext in exts:
            path = FIGURES / "{}.{}".format(stem, ext)
            if not path.exists():
                print("   [MISSING] {}".format(path.name))
                ok = False
                continue
            kb = path.stat().st_size / 1024
            if ext == "png":
                w, h, dpi = png_size(path)
                note = "{} x {} px @ {} dpi  ({:.0f} x {:.0f} mm printed)".format(
                    w, h, dpi, w / dpi * 25.4, h / dpi * 25.4) if dpi else \
                    "{} x {} px".format(w, h)
                flag = "[OK]" if dpi and dpi >= 300 else "[CHECK DPI]"
                if not (dpi and dpi >= 300):
                    ok = False
                print("   {} {:<34} {:>8.0f} KB  {}".format(
                    flag, path.name, kb, note))
            else:
                print("   [OK] {:<34} {:>8.0f} KB".format(path.name, kb))

    print("\n" + "=" * 78)
    print("All expected files present at 300 dpi." if ok
          else "SOME FILES MISSING OR BELOW 300 DPI -- see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
