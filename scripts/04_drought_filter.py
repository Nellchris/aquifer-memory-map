"""Check drought-window coverage and print the go/no-go gate table.

For a sample of stations per medium, confirm the chronicle runs through
2022-06-01 - 2025-12-31 with no gap longer than MAX_GAP_DAYS, then extrapolate
the survival rate to the full group.

Writes data/station_counts.json.
"""
import collections
import csv
import datetime as dt
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bdlisa  # noqa: E402
from hubeau import DATA, DELAY, HubeauUnreachable, get, save_json  # noqa: E402

DROUGHT_START = "2022-06-01"
DROUGHT_END = "2025-12-31"
MAX_GAP_DAYS = 62          # "no gap > 2 months"
SAMPLE_PER_GROUP = 20
SEED = 20220601


def coverage_ok(code_bss):
    """(ok, reason) for one station over the drought window."""
    body = get(
        "chroniques",
        code_bss=code_bss,
        date_debut_mesure=DROUGHT_START,
        date_fin_mesure=DROUGHT_END,
        fields="date_mesure",
        size=20000,
    )
    rows = body.get("data") or []
    if not rows:
        return False, "no_data_in_window"
    dates = sorted({dt.date.fromisoformat(r["date_mesure"][:10]) for r in rows})

    start = dt.date.fromisoformat(DROUGHT_START)
    end = dt.date.fromisoformat(DROUGHT_END)
    if (dates[0] - start).days > MAX_GAP_DAYS:
        return False, "starts_late"
    if (end - dates[-1]).days > MAX_GAP_DAYS:
        return False, "ends_early"
    gap = max((b - a).days for a, b in zip(dates, dates[1:])) if len(dates) > 1 else 0
    if gap > MAX_GAP_DAYS:
        return False, f"gap_{gap}d"
    return True, "ok"


def main():
    path = DATA / "stations_classified.csv"
    if not path.exists():
        sys.exit("data/stations_classified.csv missing -- run 03_classify_bdlisa.py first")
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    by_group = collections.defaultdict(list)
    for r in rows:
        if r["aquifer_medium"] in bdlisa.POSTER_GROUPS:
            by_group[r["aquifer_medium"]].append(r)

    rng = random.Random(SEED)
    results = {}
    for group in bdlisa.POSTER_GROUPS:
        pool = by_group.get(group, [])
        sample = rng.sample(pool, min(SAMPLE_PER_GROUP, len(pool)))
        print(f"\n{group}: {len(pool)} stations, testing {len(sample)}")
        reasons = collections.Counter()
        passed = []
        for i, st in enumerate(sample, 1):
            ok, why = coverage_ok(st["code_bss"])
            reasons[why] += 1
            if ok:
                passed.append(st["code_bss"])
            print(f"  [{i:2}/{len(sample)}] {st['code_bss']:16} {why}")
            time.sleep(DELAY)
        rate = len(passed) / len(sample) if sample else 0.0
        results[group] = {
            "after_record_filter": len(pool),
            "sample_size": len(sample),
            "sample_passed": len(passed),
            "pass_rate": round(rate, 3),
            "estimated_after_drought_filter": int(round(len(pool) * rate)),
            "reasons": dict(reasons),
            "passing_sample_codes": passed,
        }

    counts = {
        "parameters": {
            "nb_mesures_piezo_min": 120,
            "drought_window": [DROUGHT_START, DROUGHT_END],
            "max_gap_days": MAX_GAP_DAYS,
            "sample_per_group": SAMPLE_PER_GROUP,
            "random_seed": SEED,
            "medium_groups": bdlisa.MEDIUM_GROUPS,
        },
        "groups": results,
    }
    save_json(counts, "station_counts.json")

    print("\n" + "=" * 62)
    print("GATE CHECK - Station Counts")
    print("=" * 62)
    print(f"{'Group':<12} {'After record filter':>20} {'After drought filter':>21}")
    verdicts = []
    for group in bdlisa.POSTER_GROUPS:
        g = results[group]
        est = g["estimated_after_drought_filter"]
        print(f"{group:<12} {g['after_record_filter']:>20} "
              f"{est:>14} (est.) ")
        verdicts.append(est)
    print("-" * 62)
    print(f"(drought column estimated from a {SAMPLE_PER_GROUP}-station sample "
          f"per group; pass rates "
          + ", ".join(f"{g}={results[g]['pass_rate']:.0%}" for g in bdlisa.POSTER_GROUPS)
          + ")")
    worst = min(verdicts)
    if worst >= 25:
        print("\nGO: all groups >= 25 after drought filter")
    elif worst >= 20:
        print("\nWATCH: a group is 20-24 -- proceed with caution, note the limitation")
    else:
        print("\nNO-GO: a group is < 20 -- widen the criteria")


if __name__ == "__main__":
    try:
        main()
    except HubeauUnreachable as exc:
        print(f"\nBLOCKED: {exc}", file=sys.stderr)
        sys.exit(2)
