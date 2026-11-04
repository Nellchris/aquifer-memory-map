"""Monthly levels, normals, drought minimum, recovery time and group statistics.

Input:  data/colab_chroniques/chroniques_all.csv  (9.6M rows, grouped by station)
        data/stations_classified.csv
Output: data/monthly_levels.csv, data/normals.csv, data/drought_min.csv,
        data/recovery.csv, data/stats_summary.json

niveau_nappe_eau is the water-table elevation in m NGF, so a LOWER value is
drier. Drought minimum is the lowest monthly median; recovery is the level
returning to at or above the calendar-month normal.

MIN_OBS_PER_MONTH is the one parameter worth arguing about. The brief asked for
10, meaning "drop unreliable monthly values", but 100 of these stations are read
weekly and 36 monthly, so a threshold of 10 drops those stations entirely rather
than dropping bad months -- and every one of them is porous, which would bias
the very comparison being made. The default here is 3, and the script runs the
whole pipeline again at 10 as a sensitivity check.
"""

import collections
import csv
import json
import statistics
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CHRONIQUES = DATA / "colab_chroniques" / "chroniques_all.csv"
SKIPPED = DATA / "colab_chroniques" / "skipped_stations.txt"
CLASSIFIED = DATA / "stations_classified.csv"

GROUPS = ("porous", "fissured", "karstic")

MIN_OBS_PER_MONTH = 3
SENSITIVITY_MIN_OBS = 10

REF_START, REF_END = "2000-01", "2019-12"
MIN_REF_YEARS = 10

DROUGHT_START, DROUGHT_END = "2022-06", "2023-03"
CENSOR_AT = "2025-12"
CONSECUTIVE = 2


def month_index(ym):
    """'2022-06' -> integer month count, for arithmetic on calendar months."""
    y, m = ym.split("-")
    return int(y) * 12 + int(m) - 1


def month_label(index):
    return "{:04d}-{:02d}".format(index // 12, index % 12 + 1)


# --------------------------------------------------------------- pass 1
def read_station_blocks():
    """Yield (code_bss, [(date, niveau, profondeur), ...]) one station at a time.

    The file is written station by station, so blocks are contiguous and this
    never holds more than one station in memory.
    """
    with CHRONIQUES.open(newline="", encoding="utf-8") as fh:
        current, rows = None, []
        for r in csv.DictReader(fh):
            code = r["code_bss"]
            if code != current:
                if current is not None:
                    yield current, rows
                current, rows = code, []
            try:
                rows.append((
                    r["date_mesure"],
                    float(r["niveau_nappe_eau"]),
                    float(r["profondeur_nappe"]) if r["profondeur_nappe"] else None,
                ))
            except ValueError:
                continue
        if current is not None:
            yield current, rows


def duplicate_level_fields(rows):
    """True if profondeur_nappe just repeats niveau_nappe_eau.

    Diagnostic only. Within a station the two should be mirrors (niveau =
    ground level minus depth), so a correlation of +1 looked at first like an
    inverted sign convention. It is not: in those stations the two fields hold
    identical values, e.g. 552.64 for both, which is plainly an elevation in m
    NGF. So profondeur is the unpopulated field and niveau is still valid.
    Since the analysis uses niveau only, these stations are kept.
    """
    pairs = [(n, p) for _, n, p in rows if p is not None]
    if len(pairs) < 30:
        return False
    same = sum(1 for n, p in pairs if abs(n - p) < 1e-9)
    return same > 0.95 * len(pairs)


def monthly_medians(rows, min_obs):
    """{'YYYY-MM': (median_level, n_obs)} keeping only months with enough obs."""
    buckets = collections.defaultdict(list)
    for date, niveau, _ in rows:
        buckets[date[:7]].append(niveau)
    return {
        ym: (statistics.median(vals), len(vals))
        for ym, vals in buckets.items()
        if len(vals) >= min_obs
    }


# --------------------------------------------------------------- pass 2
def compute_normals(monthly):
    """Per calendar month: median, p25, p75, n_years over the reference period.

    Returns None if any calendar month has fewer than MIN_REF_YEARS years.
    """
    by_cal = collections.defaultdict(list)
    for ym, (level, _n) in monthly.items():
        if REF_START <= ym <= REF_END:
            by_cal[int(ym.split("-")[1])].append(level)

    normals = {}
    for cal in range(1, 13):
        vals = by_cal.get(cal, [])
        if len(vals) < MIN_REF_YEARS:
            return None
        arr = np.array(vals)
        normals[cal] = {
            "median_normal": float(np.median(arr)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "n_years": len(vals),
        }
    return normals


def drought_minimum(monthly, normals):
    """Lowest monthly median in the drought window, with its departure."""
    window = {ym: v for ym, v in monthly.items() if DROUGHT_START <= ym <= DROUGHT_END}
    if not window:
        return None
    min_ym = min(window, key=lambda ym: window[ym][0])
    min_level = window[min_ym][0]
    normal = normals[int(min_ym.split("-")[1])]["median_normal"]
    return {
        "min_date": min_ym,
        "min_level": min_level,
        "normal_for_month": normal,
        "departure": min_level - normal,
    }


def recovery(monthly, normals, min_ym):
    """First month starting a run of CONSECUTIVE months at or above normal.

    Scans forward from the drought minimum. A month that is missing from
    `monthly` breaks the run, since being above normal cannot be confirmed.
    Returns (recovery_ym or None, months_from_min or None).
    """
    start = month_index(min_ym)
    last = max(month_index(ym) for ym in monthly)

    run_start = None
    run = 0
    for idx in range(start, last + 1):
        ym = month_label(idx)
        entry = monthly.get(ym)
        if entry is None:
            run, run_start = 0, None
            continue
        level = entry[0]
        if level >= normals[idx % 12 + 1]["median_normal"]:
            if run == 0:
                run_start = ym
            run += 1
            if run >= CONSECUTIVE:
                return run_start, month_index(run_start) - start
        else:
            run, run_start = 0, None
    return None, None


# --------------------------------------------------------------- stats
def dunn_bonferroni(samples):
    """Dunn's post-hoc test with Bonferroni correction.

    z = (Rbar_i - Rbar_j) / sqrt( [N(N+1)/12 - T/(12(N-1))] * (1/n_i + 1/n_j) )
    with T = sum(t^3 - t) over tie groups (Zar, Biostatistical Analysis).
    """
    names = list(samples)
    pooled = np.concatenate([samples[k] for k in names])
    ranks = stats.rankdata(pooled)
    total = len(pooled)

    _vals, counts = np.unique(pooled, return_counts=True)
    ties = float(np.sum(counts ** 3 - counts))

    mean_ranks, sizes, offset = {}, {}, 0
    for name in names:
        n = len(samples[name])
        mean_ranks[name] = float(np.mean(ranks[offset:offset + n]))
        sizes[name] = n
        offset += n

    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    base = total * (total + 1) / 12.0 - ties / (12.0 * (total - 1))

    out = {}
    for a, b in pairs:
        se = np.sqrt(base * (1.0 / sizes[a] + 1.0 / sizes[b]))
        z = (mean_ranks[a] - mean_ranks[b]) / se
        p = 2.0 * stats.norm.sf(abs(z))
        out["{} vs {}".format(a, b)] = {
            "z": round(float(z), 4),
            "p_unadjusted": float(p),
            "p_bonferroni": float(min(1.0, p * len(pairs))),
        }
    return out


def describe(values):
    arr = np.array(values, dtype=float)
    q1, q3 = np.percentile(arr, [25, 75])
    return {
        "n": int(arr.size),
        "median_recovery_months": float(np.median(arr)),
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(q3 - q1),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": round(float(arr.mean()), 3),
    }


# --------------------------------------------------------------- pipeline
def run(min_obs, verbose=True, write_outputs=True):
    medium = {}
    for r in csv.DictReader(CLASSIFIED.open(encoding="utf-8")):
        medium[r["code_bss"]] = r["aquifer_medium"]

    monthly_rows, normals_rows, drought_rows, recovery_rows = [], [], [], []
    tally = collections.Counter()
    anomalies = []
    station_monthly = {}

    for code, rows in read_station_blocks():
        tally["stations_in_file"] += 1
        group = medium.get(code)
        if group not in GROUPS:
            tally["not_in_study_groups"] += 1
            continue

        if duplicate_level_fields(rows):
            # Kept: only profondeur is affected, and it is not used here.
            anomalies.append((code, group))
            tally["profondeur_duplicates_niveau"] += 1

        monthly = monthly_medians(rows, min_obs)
        if not monthly:
            tally["dropped_no_month_meets_min_obs"] += 1
            tally["dropped_no_month_" + group] += 1
            continue
        tally["has_monthly_data"] += 1
        station_monthly[code] = monthly
        if write_outputs:
            for ym, (level, n) in sorted(monthly.items()):
                monthly_rows.append({
                    "code_bss": code, "year_month": ym,
                    "median_level": round(level, 4), "n_observations": n,
                })

        normals = compute_normals(monthly)
        if normals is None:
            tally["dropped_normals_filter"] += 1
            tally["normals_fail_" + group] += 1
            continue
        tally["survived_normals"] += 1
        tally["normals_ok_" + group] += 1
        if write_outputs:
            for cal, v in normals.items():
                normals_rows.append({
                    "code_bss": code, "month": cal,
                    "median_normal": round(v["median_normal"], 4),
                    "p25": round(v["p25"], 4), "p75": round(v["p75"], 4),
                    "n_years": v["n_years"],
                })

        dmin = drought_minimum(monthly, normals)
        if dmin is None:
            tally["dropped_no_drought_window_data"] += 1
            continue
        tally["survived_drought_window"] += 1
        tally["drought_ok_" + group] += 1
        if write_outputs:
            drought_rows.append({
                "code_bss": code, "min_date": dmin["min_date"],
                "min_level": round(dmin["min_level"], 4),
                "normal_for_month": round(dmin["normal_for_month"], 4),
                "departure": round(dmin["departure"], 4),
            })

        rec_ym, rec_months = recovery(monthly, normals, dmin["min_date"])
        censored = rec_ym is None or rec_ym > CENSOR_AT
        recovery_rows.append({
            "code_bss": code,
            "aquifer_medium": group,
            "min_date": dmin["min_date"],
            "recovery_date": "" if censored else rec_ym,
            "recovery_months": "" if censored else rec_months,
            "censored": censored,
            # Kept because the series runs to late 2026: a station censored at
            # the brief's Dec 2025 horizon may still have a known recovery.
            "recovery_date_uncapped": rec_ym or "",
            "recovery_months_uncapped": "" if rec_months is None else rec_months,
        })

    if write_outputs:
        def dump(rows, name):
            path = DATA / name
            with path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            if verbose:
                print("  wrote {} ({} rows)".format(name, len(rows)))

        dump(monthly_rows, "monthly_levels.csv")
        dump(normals_rows, "normals.csv")
        dump(drought_rows, "drought_min.csv")
        dump(recovery_rows, "recovery.csv")

    return tally, recovery_rows, anomalies


def analyse(recovery_rows):
    """Group descriptives, Kruskal-Wallis and Dunn's, from recovery rows."""
    by_group = collections.defaultdict(list)
    censored = collections.Counter()
    for r in recovery_rows:
        g = r["aquifer_medium"]
        if r["censored"]:
            censored[g] += 1
        else:
            by_group[g].append(float(r["recovery_months"]))

    per_group = {}
    for g in GROUPS:
        vals = by_group.get(g, [])
        entry = describe(vals) if vals else {"n": 0}
        entry["n_censored"] = censored.get(g, 0)
        entry["n_total"] = entry["n"] + entry["n_censored"]
        entry["censored_fraction"] = (
            round(entry["n_censored"] / entry["n_total"], 4) if entry["n_total"] else None
        )
        per_group[g] = entry

    usable = {g: np.array(by_group[g]) for g in GROUPS if len(by_group.get(g, [])) >= 2}
    result = {"groups": per_group}
    if len(usable) >= 2:
        h, p = stats.kruskal(*[usable[g] for g in usable])
        result["kruskal_wallis"] = {
            "H": round(float(h), 4),
            "p_value": float(p),
            "df": len(usable) - 1,
            "groups_tested": list(usable),
            "n_total": int(sum(len(v) for v in usable.values())),
        }
        if p < 0.05:
            result["dunn_bonferroni"] = dunn_bonferroni(usable)
        else:
            result["dunn_bonferroni"] = None
    return result


def main():
    print("Reading {}".format(CHRONIQUES.name))
    print("MIN_OBS_PER_MONTH = {} (sensitivity run at {})\n".format(
        MIN_OBS_PER_MONTH, SENSITIVITY_MIN_OBS))

    tally, recovery_rows, anomalies = run(MIN_OBS_PER_MONTH)
    result = analyse(recovery_rows)

    if anomalies:
        by_group = collections.Counter(g for _c, g in anomalies)
        print("\n  profondeur_nappe duplicates niveau_nappe_eau at {} stations "
              "({}) -- kept, niveau is valid".format(len(anomalies), dict(by_group)))

    print("\nSensitivity: re-running with MIN_OBS_PER_MONTH = {}".format(
        SENSITIVITY_MIN_OBS))
    tally10, recovery10, _ = run(SENSITIVITY_MIN_OBS, verbose=False, write_outputs=False)
    result10 = analyse(recovery10)

    skipped_note = []
    if SKIPPED.exists():
        skipped_note = [
            l.strip() for l in SKIPPED.read_text(encoding="utf-8").splitlines()[1:]
            if l.strip()
        ]

    summary = {
        "parameters": {
            "min_obs_per_month": MIN_OBS_PER_MONTH,
            "min_obs_per_month_rationale": (
                "brief asked 10; 100 stations are read weekly and 36 monthly, and "
                "all stations lost at 10 are porous, so 10 would bias the "
                "between-group comparison. Sensitivity run reported separately."
            ),
            "reference_period": [REF_START, REF_END],
            "min_reference_years_per_calendar_month": MIN_REF_YEARS,
            "drought_window": [DROUGHT_START, DROUGHT_END],
            "recovery_rule": (
                "first of {} consecutive months with monthly median >= calendar-month "
                "normal; a missing month breaks the run".format(CONSECUTIVE)
            ),
            "censor_at": CENSOR_AT,
        },
        "station_flow": dict(sorted(tally.items())),
        "stations_skipped_at_fetch": skipped_note,
        "profondeur_duplicates_niveau_kept": [
            {"code_bss": c, "aquifer_medium": g} for c, g in anomalies
        ],
        "primary": result,
        "sensitivity_min_obs_10": {
            "station_flow": dict(sorted(tally10.items())),
            **result10,
        },
    }
    out = DATA / "stats_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  wrote stats_summary.json")

    report(tally, result, result10, anomalies, skipped_note)


def report(tally, result, result10, anomalies, skipped_note):
    bar = "=" * 74
    print("\n" + bar)
    print("ANALYSIS SUMMARY")
    print(bar)
    print("  stations targeted                       1320")
    print("  skipped at fetch (no data)              {}".format(len(skipped_note)))
    print("  stations present in chroniques_all.csv  {}".format(
        tally["stations_in_file"]))
    print("  profondeur duplicates niveau (kept)     {}".format(len(anomalies)))
    print("  with usable monthly data                {}".format(
        tally["has_monthly_data"]))
    print("  survived normals filter                 {}".format(
        tally["survived_normals"]))
    print("  survived drought-window filter          {}".format(
        tally["survived_drought_window"]))

    print("\n" + "-" * 74)
    print("RECOVERY BY AQUIFER MEDIUM (metropolitan, uncensored)")
    print("-" * 74)
    print("{:<10}|{:>5} |{:>9} |{:>8} |{:>11} |{:>12}".format(
        "Group", "n", "censored", "median", "IQR", "min-max"))
    print("-" * 74)
    for g in GROUPS:
        e = result["groups"][g]
        if not e["n"]:
            print("{:<10}|{:>5} |{:>9} |{:>8} |{:>11} |{:>12}".format(
                g.capitalize(), 0, e["n_censored"], "-", "-", "-"))
            continue
        print("{:<10}|{:>5} |{:>9} |{:>8.1f} |{:>11} |{:>12}".format(
            g.capitalize(), e["n"], e["n_censored"], e["median_recovery_months"],
            "{:.1f}-{:.1f}".format(e["q1"], e["q3"]),
            "{:.0f}-{:.0f}".format(e["min"], e["max"])))
    print("-" * 74)
    for g in GROUPS:
        e = result["groups"][g]
        if e["censored_fraction"] is not None:
            print("  {:<9} censored {}/{} ({:.0%})".format(
                g, e["n_censored"], e["n_total"], e["censored_fraction"]))

    kw = result.get("kruskal_wallis")
    if kw:
        print("\nKruskal-Wallis H = {:.4f}, p = {:.3e}, df = {}".format(
            kw["H"], kw["p_value"], kw["df"]))
    dunn = result.get("dunn_bonferroni")
    if dunn:
        print("Dunn's post-hoc (Bonferroni):")
        for pair, v in dunn.items():
            print("  {:<26} z = {:+7.3f}   p = {:.3e}".format(
                pair, v["z"], v["p_bonferroni"]))
    elif kw:
        print("Kruskal-Wallis not significant at 0.05; no post-hoc run.")

    kw10 = result10.get("kruskal_wallis")
    print("\nSensitivity (MIN_OBS_PER_MONTH = {}):".format(SENSITIVITY_MIN_OBS))
    for g in GROUPS:
        e = result10["groups"][g]
        med = e.get("median_recovery_months")
        print("  {:<9} n = {:<5} median = {}".format(
            g, e["n"], "{:.1f}".format(med) if med is not None else "-"))
    if kw10:
        print("  Kruskal-Wallis H = {:.4f}, p = {:.3e}".format(
            kw10["H"], kw10["p_value"]))


if __name__ == "__main__":
    main()
