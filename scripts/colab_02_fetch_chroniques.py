"""
Hub'Eau piezometry time-series fetch — paste into a single Google Colab cell.

Upload stations_classified.csv to the Colab working directory first, then run
this. It writes chroniques_all.csv, skipped_stations.txt and
chroniques_output.zip.

Note on "monthly": the chroniques endpoint returns one row per measurement,
which for many stations is daily or sub-daily, not monthly. This script saves
the raw series by default so nothing is lost. Set MONTHLY_MEAN = True to
collapse to one mean value per station-month on the way out.

Safe to re-run: stations already present in chroniques_all.csv are skipped, so
a Colab disconnect part-way through costs only the station in flight.
"""

import csv
import json
import os
import time
import zipfile

import requests

CHRONIQUES = "https://hubeau.eaufrance.fr/api/v1/niveaux_nappes/chroniques"

STATIONS_CSV = "stations_classified.csv"
OUT_CSV = "chroniques_all.csv"
SKIPPED_TXT = "skipped_stations.txt"
ZIP_OUT = "chroniques_output.zip"

GROUPS = ("porous", "fissured", "karstic")
DATE_DEBUT = "2000-01-01"
START_BY = "2010-01-01"      # station's first measurement on or before this
END_AFTER = "2025-01-01"     # station's last measurement on or after this

PAGE_SIZE = 20000
DELAY = 0.5                  # between stations, not between pages
ATTEMPTS = 3
TIMEOUT = 300
PROGRESS_EVERY = 50
MONTHLY_MEAN = False

CSV_FIELDS = ["code_bss", "date_mesure", "niveau_nappe_eau", "profondeur_nappe"]


def is_metropolitan(code_dept):
    return bool(code_dept) and str(code_dept)[:2] not in ("97", "98")


def load_stations():
    """The station list, after the three filters that define the study set."""
    with open(STATIONS_CSV, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    print("{}: {} rows".format(STATIONS_CSV, len(rows)))

    rows = [r for r in rows if r["aquifer_medium"] in GROUPS]
    print("  after medium filter (porous/fissured/karstic): {}".format(len(rows)))

    rows = [r for r in rows if is_metropolitan(r.get("code_departement"))]
    print("  after metropolitan filter:                     {}".format(len(rows)))

    # The gate's Final column applied this date filter too; without it the set
    # is 3553 stations rather than 1320, nearly three times the runtime.
    rows = [
        r for r in rows
        if r.get("date_debut") and r["date_debut"] <= START_BY
        and r.get("date_fin") and r["date_fin"] >= END_AFTER
    ]
    print("  after date filter (start <= {}, end >= {}): {}".format(
        START_BY, END_AFTER, len(rows)))

    by_group = {}
    for r in rows:
        by_group[r["aquifer_medium"]] = by_group.get(r["aquifer_medium"], 0) + 1
    print("  by medium: {}".format(by_group))
    return rows


def already_done():
    """code_bss values already written, so a re-run resumes instead of redoing."""
    if not os.path.exists(OUT_CSV):
        return set()
    done = set()
    with open(OUT_CSV, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            done.add(row["code_bss"])
    if done:
        print("\nResuming: {} stations already in {}".format(len(done), OUT_CSV))
    return done


def fetch(url, params=None):
    """GET one page, retrying with exponential backoff. Returns the JSON body."""
    last_error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT)
            if response.status_code in (200, 206):
                return response.json()
            last_error = "HTTP {}: {}".format(
                response.status_code, response.text[:200])
        except (requests.exceptions.RequestException, ValueError) as exc:
            last_error = "{}: {}".format(type(exc).__name__, exc)

        if attempt < ATTEMPTS:
            time.sleep(DELAY * (2 ** attempt))

    raise RuntimeError(last_error or "unknown error")


def fetch_station(code_bss):
    """Every measurement for one station, following pagination."""
    params = {
        "code_bss": code_bss,
        "date_debut_mesure": DATE_DEBUT,
        "size": PAGE_SIZE,
    }
    body = fetch(CHRONIQUES, params)
    rows = list(body.get("data") or [])

    next_url = body.get("next")
    while next_url:
        body = fetch(next_url)
        page = body.get("data") or []
        if not page:
            break
        rows.extend(page)
        next_url = body.get("next")

    return rows


def to_monthly(rows):
    """One mean level per station-month, for MONTHLY_MEAN."""
    buckets = {}
    for r in rows:
        month = str(r["date_mesure"])[:7]
        key = (r["code_bss"], month)
        bucket = buckets.setdefault(key, {"niveau": [], "prof": []})
        for field, name in (("niveau_nappe_eau", "niveau"),
                            ("profondeur_nappe", "prof")):
            value = r.get(field)
            if value not in (None, ""):
                try:
                    bucket[name].append(float(value))
                except (TypeError, ValueError):
                    pass

    out = []
    for (code_bss, month), bucket in sorted(buckets.items()):
        niveau = bucket["niveau"]
        prof = bucket["prof"]
        out.append({
            "code_bss": code_bss,
            "date_mesure": month + "-01",
            "niveau_nappe_eau": round(sum(niveau) / len(niveau), 4) if niveau else "",
            "profondeur_nappe": round(sum(prof) / len(prof), 4) if prof else "",
        })
    return out


def main():
    stations = load_stations()
    if not stations:
        raise SystemExit("No stations left after filtering — check the input CSV.")

    done = already_done()
    todo = [r for r in stations if r["code_bss"] not in done]

    per_station = DELAY + 1.0  # delay plus a rough API response time
    minutes = len(todo) * per_station / 60.0
    print("\n{} stations to fetch.".format(len(todo)))
    print("Expect roughly {:.0f}-{:.0f} minutes ({:.1f}s per station: {}s delay "
          "plus response time).".format(minutes, minutes * 1.8, per_station, DELAY))
    print("Keep this Colab tab open. A disconnect is recoverable — just re-run "
          "the cell and it resumes.\n")

    write_header = not os.path.exists(OUT_CSV)
    skipped = []
    fetched = 0
    total_rows = 0
    started = time.time()

    with open(OUT_CSV, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()

        for index, station in enumerate(todo, 1):
            code_bss = station["code_bss"]
            try:
                rows = fetch_station(code_bss)
            except Exception as exc:
                skipped.append((code_bss, station["aquifer_medium"], str(exc)[:160]))
                print("  SKIP {} ({}): {}".format(
                    code_bss, station["aquifer_medium"], str(exc)[:110]))
                time.sleep(DELAY)
                continue

            if not rows:
                skipped.append((code_bss, station["aquifer_medium"], "no data returned"))
                print("  SKIP {} ({}): no data returned".format(
                    code_bss, station["aquifer_medium"]))
                time.sleep(DELAY)
                continue

            clean = [{
                "code_bss": r.get("code_bss") or code_bss,
                "date_mesure": r.get("date_mesure"),
                "niveau_nappe_eau": r.get("niveau_nappe_eau"),
                "profondeur_nappe": r.get("profondeur_nappe"),
            } for r in rows if r.get("date_mesure")]

            if MONTHLY_MEAN:
                clean = to_monthly(clean)

            writer.writerows(clean)
            handle.flush()
            fetched += 1
            total_rows += len(clean)

            if index % PROGRESS_EVERY == 0 or index == len(todo):
                elapsed = time.time() - started
                rate = elapsed / index
                remaining = (len(todo) - index) * rate / 60.0
                print("Fetched {}/{} stations... {} rows so far, "
                      "{:.1f} min elapsed, ~{:.1f} min left".format(
                          index, len(todo), total_rows, elapsed / 60.0, remaining))

            time.sleep(DELAY)

    with open(SKIPPED_TXT, "w", encoding="utf-8") as handle:
        if skipped:
            handle.write("code_bss\taquifer_medium\treason\n")
            for code_bss, medium, reason in skipped:
                handle.write("{}\t{}\t{}\n".format(code_bss, medium, reason))
        else:
            handle.write("No stations skipped.\n")

    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(OUT_CSV)
        archive.write(SKIPPED_TXT)

    csv_mb = os.path.getsize(OUT_CSV) / 1e6
    zip_mb = os.path.getsize(ZIP_OUT) / 1e6

    print("\n" + "=" * 58)
    print("SUMMARY")
    print("=" * 58)
    print("  stations requested        {:>10}".format(len(todo)))
    print("  stations fetched          {:>10}".format(fetched))
    print("  stations skipped          {:>10}".format(len(skipped)))
    print("  rows written this run     {:>10}".format(total_rows))
    print("  monthly aggregation       {:>10}".format(
        "on" if MONTHLY_MEAN else "off (raw series)"))
    print("  {:<24} {:>7.1f} MB".format(OUT_CSV, csv_mb))
    print("  {:<24} {:>7.1f} MB".format(ZIP_OUT, zip_mb))
    print("  elapsed                   {:>8.1f} min".format(
        (time.time() - started) / 60.0))
    if skipped:
        print("\n  see {} for the {} failures".format(SKIPPED_TXT, len(skipped)))

    print("\nDONE — download chroniques_output.zip")

    try:
        from google.colab import files
        files.download(ZIP_OUT)
    except Exception:
        pass


main()
