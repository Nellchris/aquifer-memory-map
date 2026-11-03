"""Fetch every French piezometer station with a long enough record.

nb_mesures_piezo_min=120 keeps stations with at least 120 measurements, the
proxy for ~10 years of monthly data. Writes data/stations_raw.json.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hubeau import HubeauUnreachable, paginate, save_json  # noqa: E402

MIN_MEASURES = 120


def main():
    print(f"Fetching stations with nb_mesures_piezo_min={MIN_MEASURES} ...")
    rows = list(paginate("stations", nb_mesures_piezo_min=MIN_MEASURES))
    print(f"\n{len(rows)} stations fetched")

    seen = {}
    for r in rows:
        seen[r.get("code_bss")] = r
    if len(seen) != len(rows):
        print(f"  deduplicated to {len(seen)} unique code_bss")

    with_code = sum(1 for r in seen.values() if r.get("codes_bdlisa"))
    print(f"  with a codes_bdlisa value: {with_code} ({with_code / len(seen):.0%})")
    print(f"  without one (need spatial join): {len(seen) - with_code}")

    save_json(list(seen.values()), "stations_raw.json")


if __name__ == "__main__":
    try:
        main()
    except HubeauUnreachable as exc:
        print(f"\nBLOCKED: {exc}", file=sys.stderr)
        sys.exit(2)
