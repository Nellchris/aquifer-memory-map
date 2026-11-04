"""Kaplan-Meier recovery curves, which use the censored stations instead of
dropping them.

Censoring is not even across groups -- 15% of karstic stations and 11% of
porous ones never recover by the Dec 2025 horizon, against 2% of fissured.
Dropping them, as the Kruskal-Wallis test must, throws away the slowest
stations in each group and does so unevenly, so the reported medians understate
porous and karstic most. The Kaplan-Meier median uses every station up to the
point it is lost.
"""
import csv, collections, json, sys
from pathlib import Path
import numpy as np

from survival import km, logrank, median_from, observation_times

sys.path.insert(0, str(Path(__file__).resolve().parent))
DATA = Path(__file__).resolve().parent.parent / "data"
GROUPS = ("porous", "fissured", "karstic")
HORIZON = 48  # months past the drought minimum that the series can cover


def main():
    rows = list(csv.DictReader((DATA / "recovery.csv").open(encoding="utf-8")))
    for r in rows:
        r["censored"] = r["censored"] == "True"

    last_month = {}
    for r in csv.DictReader((DATA / "monthly_levels.csv").open(encoding="utf-8")):
        cb, ym = r["code_bss"], r["year_month"]
        if cb not in last_month or ym > last_month[cb]:
            last_month[cb] = ym

    data = {}
    print("Kaplan-Meier recovery (censored stations retained)\n")
    print(f"  {'group':<10} {'n':>5} {'events':>7} {'censored':>9} "
          f"{'KM median':>10} {'still unrecovered @24mo':>24}")
    summary = {}
    for g in GROUPS:
        sub = [r for r in rows if r["aquifer_medium"] == g]
        times, events = observation_times(sub, last_month)
        data[g] = (times, events)
        curve = km(times, events)
        med = median_from(curve)
        at24 = next((s for t, s, *_ in reversed(curve) if t <= 24), 1.0)
        n_ev = sum(events)
        print(f"  {g:<10} {len(times):>5} {n_ev:>7} {len(times)-n_ev:>9} "
              f"{str(med):>10} {at24:>23.1%}")
        summary[g] = {
            "n": len(times), "events": n_ev, "censored": len(times) - n_ev,
            "km_median_months": med,
            "unrecovered_at_24_months": round(float(at24), 4),
        }

    lr = logrank(data)
    print("\nPairwise log-rank (Bonferroni):")
    for pair, v in lr.items():
        print(f"  {pair:<26} chi2 = {v['chi2']:>8.3f}   p = {v['p_bonferroni']:.3e}")

    (DATA / "survival_summary.json").write_text(
        json.dumps({"groups": summary, "logrank_bonferroni": lr,
                    "note": "each censored station contributes its own "
                            "observation time: months from its drought minimum "
                            "to the earlier of Dec 2025 and the end of its record"},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote data/survival_summary.json")


if __name__ == "__main__":
    main()
