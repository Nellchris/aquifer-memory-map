"""Depth-matched recovery, with severity standardised by local variability.

The earlier matching in 05a_sensitivity.py banded stations on absolute metres
below normal. That is not comparable across media: the median normal-band IQR
is 0.47 m for porous, 0.69 m for fissured and 0.87 m for karstic, and karst
piezometers routinely swing tens of metres, so a 1 m drop is severe in an
alluvial aquifer and ordinary in a karst conduit. Matching on metres therefore
compared unlike with unlike, and it is what produced the apparent ranking
reversal in the deepest band.

Here severity is departure divided by the station's own normal-band IQR
(the median of p75 - p25 across its twelve calendar months), so a band means
the same thing in every medium.

Writes data/depth_matched_standardised.csv and returns the band summaries that
06_figures.py plots and 05d_update_stats.py folds into stats_summary.json.
"""

import collections
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GROUPS = ("porous", "fissured", "karstic")

# Bands are magnitudes below normal, in units of the station's own IQR.
BANDS = [
    ("Mild", 0.25, 1.0),
    ("Moderate", 1.0, 2.0),
    ("Severe", 2.0, 6.0),
]
MIN_IQR = 0.01   # metres; below this the ratio is meaningless
OUT_CSV = DATA / "depth_matched_standardised.csv"


def load():
    """Per station: medium, departure, normal-band IQR, recovery, censoring."""
    iqr = {}
    per_month = collections.defaultdict(list)
    for r in csv.DictReader((DATA / "normals.csv").open(encoding="utf-8")):
        per_month[r["code_bss"]].append(float(r["p75"]) - float(r["p25"]))
    for code, spreads in per_month.items():
        iqr[code] = float(np.median(spreads))

    departure = {
        r["code_bss"]: float(r["departure"])
        for r in csv.DictReader((DATA / "drought_min.csv").open(encoding="utf-8"))
    }

    rows = []
    for r in csv.DictReader((DATA / "recovery.csv").open(encoding="utf-8")):
        code = r["code_bss"]
        if code not in departure or code not in iqr:
            continue
        rows.append({
            "code_bss": code,
            "aquifer_medium": r["aquifer_medium"],
            "departure_m": departure[code],
            "iqr_normal_m": iqr[code],
            "censored": r["censored"] == "True",
            "recovery_months": (None if r["censored"] == "True"
                                else int(r["recovery_months"])),
        })
    return rows


def band_for(magnitude):
    for name, lo, hi in BANDS:
        if lo <= magnitude < hi:
            return name
    return ""


def annotate(rows):
    """Add standardised severity and band; drop stations with a degenerate IQR."""
    kept, dropped = [], 0
    for r in rows:
        if r["iqr_normal_m"] <= MIN_IQR:
            dropped += 1
            continue
        sd = r["departure_m"] / r["iqr_normal_m"]
        r["standardised_departure"] = round(sd, 4)
        # Magnitude below normal; stations at or above normal get 0.
        r["severity_iqr"] = round(max(0.0, -sd), 4)
        r["band"] = band_for(r["severity_iqr"])
        kept.append(r)
    return kept, dropped


def summarise(rows):
    out = {}
    for name, lo, hi in BANDS:
        in_band = [r for r in rows if r["band"] == name]
        entry = {"band": name, "range_iqr": [lo, hi], "groups": {}}
        usable = {}
        for g in GROUPS:
            vals = [r["recovery_months"] for r in in_band
                    if r["aquifer_medium"] == g and r["recovery_months"] is not None]
            censored = sum(1 for r in in_band
                           if r["aquifer_medium"] == g and r["censored"])
            e = {"n": len(vals), "n_censored": censored}
            if vals:
                a = np.array(vals, dtype=float)
                e.update(median=float(np.median(a)),
                         q1=float(np.percentile(a, 25)),
                         q3=float(np.percentile(a, 75)))
                if len(vals) >= 2:
                    usable[g] = a
            else:
                e.update(median=None, q1=None, q3=None)
            entry["groups"][g] = e

        if len(usable) >= 2:
            h, p = stats.kruskal(*usable.values())
            entry["kruskal"] = {"H": round(float(h), 3), "p": float(p),
                                "groups_tested": list(usable)}
        ranked = [g for g in GROUPS if entry["groups"][g]["median"] is not None]
        entry["order_fastest_to_slowest"] = sorted(
            ranked, key=lambda g: entry["groups"][g]["median"])
        out[name] = entry
    return out


def main():
    rows = load()
    rows, dropped = annotate(rows)
    print("{} stations with a usable normal-band IQR ({} dropped as degenerate)"
          .format(len(rows), dropped))

    print("\nnormal-band IQR by medium (the reason metres are not comparable):")
    for g in GROUPS:
        v = np.array([r["iqr_normal_m"] for r in rows if r["aquifer_medium"] == g])
        print("   {:<9} median {:.2f} m   (n={})".format(g, np.median(v), len(v)))

    print("\nseverity by medium, raw vs standardised:")
    for g in GROUPS:
        sub = [r for r in rows if r["aquifer_medium"] == g]
        raw = np.median([r["departure_m"] for r in sub])
        std = np.median([r["standardised_departure"] for r in sub])
        print("   {:<9} raw {:+.2f} m     standardised {:+.2f} IQR".format(g, raw, std))

    fields = ["code_bss", "aquifer_medium", "departure_m", "iqr_normal_m",
              "standardised_departure", "severity_iqr", "band",
              "recovery_months", "censored"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "recovery_months": (
                "" if r["recovery_months"] is None else r["recovery_months"])})
    print("\nwrote {} ({} rows)".format(OUT_CSV.name, len(rows)))

    summary = summarise(rows)
    (DATA / "depth_matched_standardised.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote depth_matched_standardised.json")

    print("\n" + "=" * 70)
    print("DEPTH-MATCHED ON STANDARDISED SEVERITY")
    print("=" * 70)
    for name, lo, hi in BANDS:
        e = summary[name]
        print("\n{} ({}-{} IQR below normal)".format(name, lo, hi))
        for g in GROUPS:
            d = e["groups"][g]
            if d["median"] is None:
                print("   {:<9} n={:<4} -".format(g, d["n"]))
                continue
            print("   {:<9} n={:<4} median {:5.1f} mo   IQR {:.0f}-{:.0f}"
                  "   ({} censored)".format(
                      g, d["n"], d["median"], d["q1"], d["q3"], d["n_censored"]))
        if "kruskal" in e:
            print("   Kruskal-Wallis H = {:.3f}, p = {:.3e}".format(
                e["kruskal"]["H"], e["kruskal"]["p"]))
        print("   fastest -> slowest: " + " < ".join(e["order_fastest_to_slowest"]))

    fastest = {summary[n]["order_fastest_to_slowest"][0] for n, _l, _h in BANDS
               if summary[n]["order_fastest_to_slowest"]}
    slowest = {summary[n]["order_fastest_to_slowest"][-1] for n, _l, _h in BANDS
               if summary[n]["order_fastest_to_slowest"]}
    print("\nfastest group in every band: {}".format(
        fastest.pop() if len(fastest) == 1 else "varies: {}".format(fastest)))
    print("slowest group in every band: {}".format(
        slowest.pop() if len(slowest) == 1 else "varies: {}".format(slowest)))


if __name__ == "__main__":
    main()
