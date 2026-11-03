"""Classify the Colab-fetched stations by aquifer medium and run the gate check.

Input:  data/colab_output/stations_with_bdlisa.csv  (from scripts/colab_fetch_stations.py)
        data/bdlisa_download/TME.csv               (from scripts/bdlisa.py)
Output: data/stations_classified.csv
        data/station_counts.json

The medium mapping comes from bdlisa.MEDIUM_GROUPS, which follows Sandre
nomenclature 353. The date filter here is approximate: it uses the station
metadata's first/last measurement dates, which say nothing about gaps in
between. 04_drought_filter.py does the real gap check on the time series.
"""

import collections
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bdlisa  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATIONS_CSV = DATA / "colab_output" / "stations_with_bdlisa.csv"
STATIONS_RAW = DATA / "colab_output" / "stations_raw.json"
TME = DATA / "bdlisa_download" / "TME.csv"

# Approximate coverage thresholds, applied to station metadata dates.
START_BY = "2010-01-01"   # >= 10 years of record before the 2020s droughts
END_AFTER = "2025-01-01"  # record still running through the recovery window

GATE_GO = 25
GATE_WATCH = 20


def load_departments():
    """{code_bss: code_departement}, for excluding the overseas departments.

    The fetch is France-wide, so it includes Reunion, Guadeloupe, Martinique,
    Mayotte and Guyane. Those sit outside the 2022 European drought entirely --
    Reunion is in the southern hemisphere -- so the poster needs metropolitan
    stations only.
    """
    if not STATIONS_RAW.exists():
        print(f"  {STATIONS_RAW.name} missing; cannot split metropolitan/overseas")
        return {}
    raw = json.loads(STATIONS_RAW.read_text(encoding="utf-8"))
    return {s.get("code_bss"): str(s.get("code_departement") or "") for s in raw}


def is_metropolitan(code_dept):
    return bool(code_dept) and code_dept[:2] not in ("97", "98")


def load_entities():
    if not TME.exists():
        return bdlisa.fetch_entity_table(dest=TME)
    return {r["CodeEH"]: r for r in csv.DictReader(TME.open(encoding="utf-8-sig"))}


def main():
    stations = list(csv.DictReader(STATIONS_CSV.open(encoding="utf-8")))
    table = load_entities()
    depts = load_departments()
    print(f"{len(stations)} stations, {len(table)} BDLISA entities")

    has_codes = [s for s in stations if s["codes_bdlisa"].strip()]
    print(f"  with codes_bdlisa:    {len(has_codes)}")
    print(f"  without codes_bdlisa: {len(stations) - len(has_codes)}")

    rows = []
    notes = collections.Counter()
    for s in stations:
        codes = [c for c in s["codes_bdlisa"].split("|") if c]
        if not codes:
            group, milieu, note, source = None, None, "no_bdlisa_code", "none"
        else:
            group, milieu, _entity, note = bdlisa.classify_codes(codes, table)
            if note.startswith("ambiguous"):
                source = "ambiguous"
            elif group is None and note == "no_bdlisa_code_in_reference":
                source = "none"
            else:
                source = "direct"
        notes[note] += 1

        rows.append({
            "code_bss": s["code_bss"],
            "x": s["x"],
            "y": s["y"],
            "aquifer_medium": group or (
                "ambiguous" if source == "ambiguous"
                else "no_bdlisa" if source == "none"
                else bdlisa.MEDIUM_GROUPS.get(str(milieu), "unknown")
            ),
            "medium_code": milieu or "",
            "date_debut": s["date_debut_mesure"],
            "date_fin": s["date_fin_mesure"],
            "bdlisa_source": source,
            "code_departement": depts.get(s["code_bss"], ""),
        })

    print("\njoin outcomes:")
    for note, n in notes.most_common():
        print(f"  {note:<44} {n:>5}")

    out_csv = DATA / "stations_classified.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out_csv}")

    # ---- filter stages -------------------------------------------------
    def passes_start(r):
        return bool(r["date_debut"]) and r["date_debut"] <= START_BY

    def passes_end(r):
        return bool(r["date_fin"]) and r["date_fin"] >= END_AFTER

    stage_counts = {}
    for label in list(bdlisa.POSTER_GROUPS) + ["mixed", "unknown", "ambiguous", "no_bdlisa"]:
        in_group = [r for r in rows if r["aquifer_medium"] == label]
        after_start = [r for r in in_group if passes_start(r)]
        final = [r for r in after_start if passes_end(r)]
        metro = [r for r in final if is_metropolitan(r["code_departement"])]
        stage_counts[label] = {
            "with_bdlisa": len(in_group),
            "after_record_filter": len(after_start),
            "final": len(final),
            "final_metropolitan": len(metro),
            "final_overseas": len(final) - len(metro),
        }

    counts = {
        "parameters": {
            "source_csv": str(STATIONS_CSV.relative_to(ROOT)),
            "stations_total": len(stations),
            "nb_mesures_piezo_min": 120,
            "date_debut_mesure_on_or_before": START_BY,
            "date_fin_mesure_on_or_after": END_AFTER,
            "filter_is_approximate": (
                "metadata first/last dates only; no gap check inside the window"
            ),
            "medium_groups": bdlisa.MEDIUM_GROUPS,
            "milieu_labels": bdlisa.MILIEU_LABELS,
            "gate_thresholds": {"go": GATE_GO, "watch": GATE_WATCH},
        },
        "join_outcomes": dict(notes.most_common()),
        "stages": stage_counts,
    }
    out_json = DATA / "station_counts.json"
    out_json.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_json}")

    # ---- gate check ----------------------------------------------------
    line = "-" * 72
    print()
    print("=" * 72)
    print("GATE CHECK - Station Counts")
    print("=" * 72)
    print(f"{'':<22}|{'With BDLISA':>13} |{'Record filter':>15} |"
          f"{'Final':>8} |{'Metropolitan':>13}")
    print(line)
    for g in bdlisa.POSTER_GROUPS:
        c = stage_counts[g]
        print(f"{g.capitalize():<22}|{c['with_bdlisa']:>13} |"
              f"{c['after_record_filter']:>15} |{c['final']:>8} |"
              f"{c['final_metropolitan']:>13}")
    print(line)
    for label, shown in (("mixed", "Mixed (excluded)"),
                         ("unknown", "Unknown (excluded)"),
                         ("ambiguous", "Ambiguous (excluded)"),
                         ("no_bdlisa", "No BDLISA code")):
        c = stage_counts[label]
        print(f"{shown:<22}|{c['with_bdlisa']:>13} |"
              f"{c['after_record_filter']:>15} |{'-':>8} |{'-':>13}")
    print(line)
    print(f"Record filter: date_debut_mesure <= {START_BY}")
    print(f"Final:         plus date_fin_mesure >= {END_AFTER}")
    print("Metropolitan:  Final minus the overseas departments (97x/98x)")

    # Gate on the metropolitan counts: the overseas departments were not in
    # the 2022 European drought.
    finals = [stage_counts[g]["final_metropolitan"] for g in bdlisa.POSTER_GROUPS]
    worst = min(finals)
    print()
    if worst >= GATE_GO:
        print(f"GO: all three groups >= {GATE_GO} in the Final column")
    elif worst >= GATE_WATCH:
        print(f"WATCH: a group is {GATE_WATCH}-{GATE_GO - 1} - proceed with "
              "caution and note the limitation")
    else:
        print(f"NO-GO: a group is < {GATE_WATCH} - widen the criteria")
    for g in bdlisa.POSTER_GROUPS:
        c = stage_counts[g]
        print(f"   {g:<10} {c['final_metropolitan']:>5} metropolitan "
              f"({c['final_overseas']} overseas excluded)")


if __name__ == "__main__":
    main()
