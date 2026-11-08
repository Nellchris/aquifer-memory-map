"""Fold the standardised depth-matched results into stats_summary.json.

Run order: 05_analyse_recovery.py -> 05a_sensitivity.py -> 05c_standardised.py
-> this. It is a separate step because 05_analyse_recovery.py rewrites
stats_summary.json from scratch, so the standardised block has to be merged in
afterwards rather than written during that pass.

Idempotent: re-running replaces the merged block rather than nesting it.
"""

import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
STATS = DATA / "stats_summary.json"
STANDARDISED = DATA / "depth_matched_standardised.json"
GROUPS = ("porous", "fissured", "karstic")


def main():
    for path in (STATS, STANDARDISED):
        if not path.exists():
            sys.exit("missing {} - run the 05 scripts first".format(path.name))

    stats = json.loads(STATS.read_text(encoding="utf-8"))
    bands = json.loads(STANDARDISED.read_text(encoding="utf-8"))

    orders = [b["order_fastest_to_slowest"] for b in bands.values()
              if b["order_fastest_to_slowest"]]
    fastest = {o[0] for o in orders}
    slowest = {o[-1] for o in orders}
    consistent = len(fastest) == 1 and len(slowest) == 1

    stats["depth_matched_standardised"] = {
        "severity_definition": (
            "departure at the drought minimum divided by the station's own "
            "normal-band IQR, the median of p75 - p25 across its twelve "
            "calendar months"
        ),
        "why": (
            "The median normal-band IQR is 0.47 m for porous, 0.69 m for "
            "fissured and 0.87 m for karstic, and karst water tables swing "
            "tens of metres naturally, so a drop of a fixed number of metres "
            "is a far milder event in karst than in an alluvial aquifer. "
            "Banding on absolute metres compared unlike with unlike."
        ),
        "source_files": ["depth_matched_standardised.csv",
                         "depth_matched_standardised.json"],
        "bands": bands,
        "fastest_in_every_band": fastest.pop() if len(fastest) == 1 else None,
        "slowest_in_every_band": slowest.pop() if len(slowest) == 1 else None,
        "ordering_consistent_across_bands": consistent,
        "supersedes": (
            "the depth bands in sensitivity.json, which were matched on "
            "absolute metres below normal"
        ),
    }

    stats["reversal_claim"] = {
        "claim": (
            "that the medium ranking reverses at deep drawdowns, with porous "
            "becoming the slowest group"
        ),
        "status": "NOT SUPPORTED",
        "arose_from": (
            "matching stations on absolute metres below normal, in "
            "sensitivity.json, where the -1.0 to -3.0 m band gave porous 15 "
            "months against karstic 11"
        ),
        "under_standardisation": (
            "the ordering is fissured < porous < karstic in all three bands, "
            "and in the Severe band porous and karstic are 15.0 and 15.5 "
            "months, effectively tied rather than reversed"
        ),
        "what_does_hold": (
            "fissured is fastest and karstic slowest in every severity band, "
            "and all three bands are significant by Kruskal-Wallis"
        ),
        "caveat": (
            "the Severe karstic cell rests on 12 uncensored stations of 20, "
            "so 8 of 20 are censored and that median is the least certain "
            "number in the figure"
        ),
    }

    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print("merged into {}".format(STATS.name))
    print("  keys now: {}".format(", ".join(sorted(stats))))
    print("\n  fastest in every band: {}".format(
        stats["depth_matched_standardised"]["fastest_in_every_band"]))
    print("  slowest in every band: {}".format(
        stats["depth_matched_standardised"]["slowest_in_every_band"]))
    print("  reversal claim:        {}".format(stats["reversal_claim"]["status"]))


if __name__ == "__main__":
    main()
