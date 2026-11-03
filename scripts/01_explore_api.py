"""Explore the Hub'Eau Piezometrie API and record its schema.

Writes data/api_schema.json so later scripts (and the poster methods section)
can be checked against what the API actually returned, rather than against
documentation.
"""
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from hubeau import DATA, HubeauUnreachable, get, save_json  # noqa: E402


def main():
    schema = {}

    print("== stations: full record ==")
    body = get("stations", size=2)
    schema["stations_count_total"] = body.get("count")
    station = body["data"][0]
    schema["stations_fields"] = sorted(station)
    print(f"total stations: {body.get('count')}")
    print(f"{len(station)} fields:")
    for k, v in sorted(station.items()):
        print(f"  {k:32} {str(v)[:70]!r}")

    print("\n== does the station record carry a BDLISA reference? ==")
    bdlisa_fields = [k for k in station if "bdlisa" in k.lower()]
    schema["bdlisa_fields"] = bdlisa_fields
    for k in bdlisa_fields:
        print(f"  {k} = {station[k]!r}")
    if not bdlisa_fields:
        print("  NONE -- classification must fall back to a spatial join.")

    print("\n== nb_mesures_piezo_min: how many stations qualify? ==")
    schema["counts_by_min_measures"] = {}
    for n in (0, 60, 120, 240):
        c = get("stations", nb_mesures_piezo_min=n, size=1, fields="code_bss")["count"]
        schema["counts_by_min_measures"][n] = c
        print(f"  nb_mesures_piezo_min={n:4} -> {c} stations")

    print("\n== chroniques: full record ==")
    code = station["code_bss"]
    jc = get("chroniques", code_bss=code, size=2)
    if jc.get("data"):
        chron = jc["data"][0]
        schema["chroniques_fields"] = sorted(chron)
        print(f"{len(chron)} fields (station {code}):")
        for k, v in sorted(chron.items()):
            print(f"  {k:32} {str(v)[:70]!r}")
    else:
        print(f"  no chronicle rows for {code}")

    save_json(schema, "api_schema.json")
    print("\nSchema written. Compare scripts/02-04 field names against it.")


if __name__ == "__main__":
    try:
        main()
    except HubeauUnreachable as exc:
        print(f"\nBLOCKED: {exc}", file=sys.stderr)
        sys.exit(2)
