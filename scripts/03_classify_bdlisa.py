"""Attach a BDLISA aquifer medium to every station.

Two paths, in order:
  1. code join -- the station's `codes_bdlisa` against BDLISA entity CodeEH.
  2. spatial join -- for stations with no usable code, point-in-polygon against
     the level-3 BDLISA polygons (downloaded only if step 1 leaves a remainder).

Writes data/stations_classified.csv and data/bdlisa_entities.json.
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bdlisa  # noqa: E402
from hubeau import DATA, save_json  # noqa: E402

ENTITIES_CACHE = DATA / "bdlisa_entities.json"
TME_CACHE = DATA / "bdlisa_download" / "TME.csv"
GEOM_CACHE = DATA / "bdlisa_download" / "EntiteHydroGeol_FXX.gpkg"


def load_entities():
    if ENTITIES_CACHE.exists():
        print(f"using cached {ENTITIES_CACHE}")
        return json.loads(ENTITIES_CACHE.read_text(encoding="utf-8"))
    table = bdlisa.fetch_entity_table(dest=TME_CACHE)
    save_json(table, ENTITIES_CACHE.name)
    return table


def spatial_fallback(unmatched, table):
    """Point-in-polygon for stations with no usable BDLISA code."""
    if not unmatched:
        return {}
    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError:
        print(f"  geopandas unavailable -- leaving {len(unmatched)} unclassified")
        return {}

    bdlisa.fetch_polygons(GEOM_CACHE)
    polys = gpd.read_file(GEOM_CACHE)
    polys = polys[polys["NiveauEH"].astype(str) == "3"]

    pts = gpd.GeoDataFrame(
        {"code_bss": [s["code_bss"] for s in unmatched]},
        geometry=[Point(s["lon"], s["lat"]) for s in unmatched],
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(pts, polys[["CodeEH", "MilieuEH", "geometry"]], how="left")
    out = {}
    for code_bss, grp in joined.groupby("code_bss"):
        media = {str(m) for m in grp["MilieuEH"].dropna()}
        groups = {bdlisa.MEDIUM_GROUPS.get(m, "unknown") for m in media}
        usable = groups & set(bdlisa.POSTER_GROUPS)
        if len(usable) == 1:
            m = next(m for m in media if bdlisa.MEDIUM_GROUPS.get(m) in usable)
            row = grp[grp["MilieuEH"].astype(str) == m].iloc[0]
            out[code_bss] = (usable.pop(), m, row["CodeEH"], "spatial_join")
    print(f"  spatial join classified {len(out)}/{len(unmatched)}")
    return out


def main():
    raw_path = DATA / "stations_raw.json"
    if not raw_path.exists():
        sys.exit("data/stations_raw.json missing -- run 02_fetch_stations.py first")
    stations = json.loads(raw_path.read_text(encoding="utf-8"))
    table = load_entities()
    print(f"{len(stations)} stations, {len(table)} BDLISA entities\n")

    rows, unmatched, notes = [], [], collections.Counter()
    for s in stations:
        group, milieu, entity, note = bdlisa.classify_codes(s.get("codes_bdlisa"), table)
        notes[note] += 1
        rec = {
            "code_bss": s.get("code_bss"),
            "lat": s.get("lat") or s.get("y"),
            "lon": s.get("lon") or s.get("x"),
            "aquifer_medium": group,
            "milieu_eh": milieu,
            "milieu_label": bdlisa.MILIEU_LABELS.get(str(milieu), ""),
            "code_entite_bdlisa": entity,
            "classification_note": note,
            "nb_mesures_piezo": s.get("nb_mesures_piezo"),
            "record_start": s.get("date_debut_mesure"),
            "record_end": s.get("date_fin_mesure"),
        }
        rows.append(rec)
        if group is None and note == "no_bdlisa_code_in_reference" and rec["lat"]:
            unmatched.append(rec)

    print("classification notes:")
    for note, n in notes.most_common():
        print(f"  {note:42} {n}")

    print(f"\nspatial fallback for {len(unmatched)} stations")
    for code_bss, (g, m, e, note) in spatial_fallback(unmatched, table).items():
        for rec in rows:
            if rec["code_bss"] == code_bss:
                rec.update(aquifer_medium=g, milieu_eh=m, code_entite_bdlisa=e,
                           milieu_label=bdlisa.MILIEU_LABELS.get(str(m), ""),
                           classification_note=note)

    import csv
    out = DATA / "stations_classified.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out}")

    counts = collections.Counter(r["aquifer_medium"] or "unclassified" for r in rows)
    print("\nstations per medium (record filter only):")
    for g in list(bdlisa.POSTER_GROUPS) + ["mixed", "unknown", "unclassified"]:
        if counts.get(g):
            print(f"  {g:14} {counts[g]}")


if __name__ == "__main__":
    main()
