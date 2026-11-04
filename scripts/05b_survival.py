"""Kaplan-Meier recovery curves, which use the censored stations instead of
dropping them.

Censoring is not even across groups -- 15% of karstic stations and 11% of
porous ones never recover by the Dec 2025 horizon, against 2% of fissured.
Dropping them, as the Kruskal-Wallis test must, throws away the slowest
stations in each group and does so unevenly, so the reported medians understate
porous and karstic most. The Kaplan-Meier median uses every station up to the
point it is lost.
"""
import csv, collections, json
from pathlib import Path
import numpy as np
from scipy import stats

DATA = Path(__file__).resolve().parent.parent / "data"
GROUPS = ("porous", "fissured", "karstic")
HORIZON = 48  # months past the drought minimum that the series can cover


def km(times, events):
    """Kaplan-Meier survival of 'not yet recovered'. events=1 means recovered."""
    order = np.argsort(times)
    times, events = np.array(times)[order], np.array(events)[order]
    at_risk = len(times)
    surv, curve = 1.0, []
    for t in np.unique(times):
        d = int(np.sum((times == t) & (events == 1)))
        c = int(np.sum((times == t) & (events == 0)))
        if at_risk > 0 and d > 0:
            surv *= 1.0 - d / at_risk
        curve.append((float(t), surv, at_risk, d, c))
        at_risk -= (d + c)
    return curve


def median_from(curve):
    for t, s, *_ in curve:
        if s <= 0.5:
            return t
    return None


def logrank(groups):
    """Pairwise log-rank chi-square, Bonferroni-adjusted."""
    names = list(groups)
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    out = {}
    for a, b in pairs:
        ta, ea = groups[a]
        tb, eb = groups[b]
        allt = np.unique(np.concatenate([ta, tb]))
        o_a = e_a = var = 0.0
        for t in allt:
            n_a = int(np.sum(np.array(ta) >= t))
            n_b = int(np.sum(np.array(tb) >= t))
            n = n_a + n_b
            d_a = int(np.sum((np.array(ta) == t) & (np.array(ea) == 1)))
            d_b = int(np.sum((np.array(tb) == t) & (np.array(eb) == 1)))
            d = d_a + d_b
            if n < 2 or d == 0:
                continue
            o_a += d_a
            e_a += d * n_a / n
            var += d * (n_a / n) * (1 - n_a / n) * (n - d) / (n - 1)
        chi = (o_a - e_a) ** 2 / var if var > 0 else 0.0
        p = float(stats.chi2.sf(chi, 1))
        out[f"{a} vs {b}"] = {
            "chi2": round(float(chi), 4),
            "p_bonferroni": float(min(1.0, p * len(pairs))),
        }
    return out


def main():
    rows = list(csv.DictReader((DATA / "recovery.csv").open(encoding="utf-8")))
    data = {}
    print("Kaplan-Meier recovery (censored stations retained)\n")
    print(f"  {'group':<10} {'n':>5} {'events':>7} {'censored':>9} "
          f"{'KM median':>10} {'still unrecovered @24mo':>24}")
    summary = {}
    for g in GROUPS:
        sub = [r for r in rows if r["aquifer_medium"] == g]
        times, events = [], []
        for r in sub:
            if r["censored"] == "True":
                times.append(HORIZON)
                events.append(0)
            else:
                times.append(int(r["recovery_months"]))
                events.append(1)
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
                    "note": "censored at the Dec 2025 horizon, encoded as "
                            f"{HORIZON} months with event=0"},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote data/survival_summary.json")


main()
