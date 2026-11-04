"""Right-censored survival helpers shared by the stats and figure scripts.

Kept in one place so data/survival_summary.json and figures/fig3 cannot drift
apart.
"""
import numpy as np
from scipy import stats


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

def month_index(ym):
    y, m = ym.split("-")
    return int(y) * 12 + int(m) - 1


def observation_times(recovery_rows, last_month, censor_at="2025-12"):
    """(times, events) per station, with a real censoring time for each.

    A censored station is not censored at some flat horizon: it is observed
    from its own drought minimum until the earlier of the analysis horizon and
    the end of its record, and is known not to have recovered in between. Using
    one flat value instead would put every censored station beyond the last
    event, which hides them from the risk set and makes the Kaplan-Meier curve
    collapse to the naive estimate.
    """
    horizon = month_index(censor_at)
    times, events = [], []
    for r in recovery_rows:
        start = month_index(r["min_date"])
        if r["censored"]:
            end = min(horizon, month_index(last_month[r["code_bss"]]))
            times.append(max(0, end - start))
            events.append(0)
        else:
            times.append(int(r["recovery_months"]))
            events.append(1)
    return times, events
