"""
Hub'Eau piezometry station fetch — paste into a single Google Colab cell.

Run this from Colab (EU/US egress), not from a blocked network. It writes
stations_raw.json, stations_with_bdlisa.csv and stations_output.zip to the
Colab working directory.
"""

import csv
import io
import json
import os
import time
import zipfile

import requests

BASE = "https://hubeau.eaufrance.fr/api/v1/niveaux_nappes/stations"
MIN_MEASURES = 120
PAGE_SIZE = 2000
DELAY = 0.5           # seconds between paginated calls
ATTEMPTS = 3          # tries per page before giving up
TIMEOUT = 180

RAW_JSON = "stations_raw.json"
CSV_OUT = "stations_with_bdlisa.csv"
ZIP_OUT = "stations_output.zip"

CSV_FIELDS = [
    "code_bss",
    "x",
    "y",
    "codes_bdlisa",
    "date_debut_mesure",
    "date_fin_mesure",
]


def fetch(url, params=None):
    """GET one page, retrying up to ATTEMPTS times. Returns the JSON body.

    Hub'Eau answers 200 on the last page and 206 (partial content) on earlier
    ones, so both are success here.
    """
    last_error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT)
            if response.status_code in (200, 206):
                return response.json()
            last_error = "HTTP {}: {}".format(
                response.status_code, response.text[:300]
            )
        except (requests.exceptions.RequestException, ValueError) as exc:
            last_error = "{}: {}".format(type(exc).__name__, exc)

        if attempt < ATTEMPTS:
            backoff = DELAY * (2 ** attempt)
            print("    attempt {}/{} failed ({}). Retrying in {:.1f}s ...".format(
                attempt, ATTEMPTS, last_error, backoff))
            time.sleep(backoff)

    raise RuntimeError(
        "Gave up on {} after {} attempts. Last error: {}".format(
            url, ATTEMPTS, last_error)
    )


def fetch_all_stations():
    """Every station with at least MIN_MEASURES measurements."""
    params = {
        "nb_mesures_piezo_min": MIN_MEASURES,
        "size": PAGE_SIZE,
        "format": "json",
    }
    print("Querying {}".format(BASE))
    print("  nb_mesures_piezo_min={}, size={}".format(MIN_MEASURES, PAGE_SIZE))

    body = fetch(BASE, params)
    total = body.get("count")
    print("  API reports {} matching stations".format(total))

    stations = []
    page = 1
    while True:
        rows = body.get("data") or []
        stations.extend(rows)
        print("  page {:>3}: +{:>5} rows  (running total {}{})".format(
            page, len(rows), len(stations),
            "/{}".format(total) if total else ""))

        next_url = body.get("next")
        if not rows or not next_url:
            break
        if total is not None and len(stations) >= total:
            break

        page += 1
        time.sleep(DELAY)
        body = fetch(next_url)

    # The API can repeat a station across pages; keep the last record for each.
    unique = {}
    for station in stations:
        unique[station.get("code_bss")] = station
    if len(unique) != len(stations):
        print("  deduplicated {} rows to {} unique code_bss".format(
            len(stations), len(unique)))

    return list(unique.values())


def bdlisa_codes(station):
    """The station's BDLISA codes, preferring codes_bdlisa over urns_bdlisa.

    Both fields are lists. urns_bdlisa holds URNs of the form
    urn:sandre:...:<code>, so the bare code is the last colon-separated part.
    """
    codes = station.get("codes_bdlisa")
    if codes:
        return [str(c) for c in codes if c]

    urns = station.get("urns_bdlisa")
    if urns:
        return [str(u).rsplit(":", 1)[-1] for u in urns if u]

    return []


def write_csv(stations):
    with open(CSV_OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for station in stations:
            writer.writerow({
                "code_bss": station.get("code_bss"),
                "x": station.get("x"),
                "y": station.get("y"),
                # pipe-joined: commas would collide with the CSV itself
                "codes_bdlisa": "|".join(bdlisa_codes(station)),
                "date_debut_mesure": station.get("date_debut_mesure"),
                "date_fin_mesure": station.get("date_fin_mesure"),
            })


def main():
    stations = fetch_all_stations()
    if not stations:
        raise SystemExit("No stations returned — check the query parameters.")

    print("\nStation record fields ({} total):".format(len(stations[0])))
    print("  " + ", ".join(sorted(stations[0])))

    with open(RAW_JSON, "w", encoding="utf-8") as handle:
        json.dump(stations, handle, ensure_ascii=False, indent=2)
    print("\nWrote {} ({:.1f} MB)".format(
        RAW_JSON, os.path.getsize(RAW_JSON) / 1e6))

    write_csv(stations)
    print("Wrote {}".format(CSV_OUT))

    with_codes = [s for s in stations if bdlisa_codes(s)]
    without = len(stations) - len(with_codes)
    multi = [s for s in with_codes if len(bdlisa_codes(s)) > 1]

    print("\n" + "=" * 58)
    print("SUMMARY")
    print("=" * 58)
    print("  total stations (>= {} measurements) {:>8}".format(
        MIN_MEASURES, len(stations)))
    print("  with a BDLISA code                 {:>8}  ({:.1%})".format(
        len(with_codes), len(with_codes) / len(stations)))
    print("  without one (need spatial join)    {:>8}  ({:.1%})".format(
        without, without / len(stations)))
    print("  with more than one BDLISA code     {:>8}  ({:.1%})".format(
        len(multi), len(multi) / len(stations)))

    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(RAW_JSON)
        archive.write(CSV_OUT)
    print("\nWrote {} ({:.1f} MB)".format(
        ZIP_OUT, os.path.getsize(ZIP_OUT) / 1e6))

    print("\nDONE — download stations_output.zip")

    # In Colab this pops the browser download; harmless anywhere else.
    try:
        from google.colab import files
        files.download(ZIP_OUT)
    except Exception:
        pass


main()
