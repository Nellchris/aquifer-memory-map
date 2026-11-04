"""Sensitivity of the recovery result to the three choices that could fake it.

Recomputes recovery from data/monthly_levels.csv and data/normals.csv, so it
does not re-read the 368 MB chronicle file.

The headline result is that karstic recovers SLOWEST, which contradicts the
hypothesis. Three things could manufacture that:

  1. consecutive-months rule -- karst oscillates hard, so demanding two
     consecutive months at or above normal may penalise flashy series
     specifically rather than measuring slower recovery.
  2. stations that never went below normal -- they score recovery = 0 and are
     concentrated in the porous group (16% of it), dragging its median down.
  3. drought depth -- karst fell 0.76 m below normal against 0.31 m for porous,
     so it simply had further to climb back.
"""

import collections
import csv
import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GROUPS = ("porous", "fissured", "karstic")
CENSOR_AT = "2025-12"


def month_index(ym):
    y, m = ym.split("-")
    return int(y) * 12 + int(m) - 1


def month_label(i):
    return "{:04d}-{:02d}".format(i // 12, i % 12 + 1)


def load():
    monthly = collections.defaultdict(dict)
    for r in csv.DictReader((DATA / "monthly_levels.csv").open(encoding="utf-8")):
        monthly[r["code_bss"]][r["year_month"]] = float(r["median_level"])

    normals = collections.defaultdict(dict)
    for r in csv.DictReader((DATA / "normals.csv").open(encoding="utf-8")):
        normals[r["code_bss"]][int(r["month"])] = float(r["median_normal"])

    dmin = {}
    for r in csv.DictReader((DATA / "drought_min.csv").open(encoding="utf-8")):
        dmin[r["code_bss"]] = {
            "min_date": r["min_date"],
            "departure": float(r["departure"]),
        }

    medium = {}
    for r in csv.DictReader((DATA / "recovery.csv").open(encoding="utf-8")):
        medium[r["code_bss"]] = r["aquifer_medium"]

    return monthly, normals, dmin, medium


def recovery_months(monthly, normals, min_ym, consecutive):
    start = month_index(min_ym)
    last = max(month_index(ym) for ym in monthly)
    run, run_start = 0, None
    for i in range(start, last + 1):
        ym = month_label(i)
        level = monthly.get(ym)
        if level is None:
            run, run_start = 0, None
            continue
        if level >= normals[i % 12 + 1]:
            if run == 0:
                run_start = ym
            run += 1
            if run >= consecutive:
                return run_start, month_index(run_start) - start
        else:
            run, run_start = 0, None
    return None, None


def test(label, consecutive=2, require_below_normal=False, depth_band=None):
    monthly, normals, dmin, medium = DATA_CACHE
    by_group = collections.defaultdict(list)
    censored = collections.Counter()

    for code, d in dmin.items():
        group = medium.get(code)
        if group not in GROUPS:
            continue
        if require_below_normal and d["departure"] >= 0:
            continue
        if depth_band is not None:
            low, high = depth_band
            if not (low <= d["departure"] < high):
                continue

        rec_ym, months = recovery_months(
            monthly[code], normals[code], d["min_date"], consecutive)
        if rec_ym is None or rec_ym > CENSOR_AT:
            censored[group] += 1
        else:
            by_group[group].append(months)

    usable = {g: np.array(by_group[g], dtype=float)
              for g in GROUPS if len(by_group.get(g, [])) >= 2}
    out = {"label": label, "groups": {}}
    for g in GROUPS:
        v = by_group.get(g, [])
        out["groups"][g] = {
            "n": len(v),
            "n_censored": censored.get(g, 0),
            "median": float(np.median(v)) if v else None,
            "q1": float(np.percentile(v, 25)) if v else None,
            "q3": float(np.percentile(v, 75)) if v else None,
        }
    if len(usable) >= 2:
        h, p = stats.kruskal(*usable.values())
        out["kruskal"] = {"H": round(float(h), 3), "p": float(p)}
    return out


def show(res):
    print("\n" + res["label"])
    print("  {:<10} {:>6} {:>10} {:>9} {:>12}".format(
        "group", "n", "censored", "median", "IQR"))
    for g in GROUPS:
        e = res["groups"][g]
        med = "-" if e["median"] is None else "{:.1f}".format(e["median"])
        iqr = "-" if e["median"] is None else "{:.0f}-{:.0f}".format(e["q1"], e["q3"])
        print("  {:<10} {:>6} {:>10} {:>9} {:>12}".format(
            g, e["n"], e["n_censored"], med, iqr))
    if "kruskal" in res:
        print("  Kruskal-Wallis H = {:.3f}, p = {:.3e}".format(
            res["kruskal"]["H"], res["kruskal"]["p"]))
    order = sorted(
        (g for g in GROUPS if res["groups"][g]["median"] is not None),
        key=lambda g: res["groups"][g]["median"])
    print("  fastest -> slowest: " + " < ".join(order))


def main():
    global DATA_CACHE
    DATA_CACHE = load()
    print("loaded {} stations with monthly data".format(len(DATA_CACHE[0])))

    results = [
        test("A. As reported (2 consecutive months, all stations)"),
        test("B. 1 month above normal instead of 2", consecutive=1),
        test("C. 3 consecutive months above normal", consecutive=3),
        test("D. Only stations that actually fell below normal",
             require_below_normal=True),
        test("E. Below normal AND 1-month rule",
             consecutive=1, require_below_normal=True),
    ]
    for r in results:
        show(r)

    # Drought depth is the remaining confound: compare like with like by
    # restricting to a common range of departure from normal.
    print("\n" + "=" * 62)
    print("Depth-matched comparison (same drought severity in each band)")
    print("=" * 62)
    bands = [(-0.5, -0.1), (-1.0, -0.5), (-3.0, -1.0)]
    for low, high in bands:
        r = test("depth band {} to {} m below normal".format(high, low),
                 require_below_normal=True, depth_band=(low, high))
        show(r)
        results.append(r)

    (DATA / "sensitivity.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote data/sensitivity.json")


if __name__ == "__main__":
    main()
