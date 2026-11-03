"""Verify the BDLISA half of the pipeline without touching Hub'Eau.

Checks classify_codes() against the real entity table and writes
data/bdlisa_medium_distribution.json, the entity-level denominator the station
counts should be read against.
"""
import collections
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bdlisa  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
TME = DATA / "bdlisa_download" / "TME.csv"


def load_table():
    if not TME.exists():
        return bdlisa.fetch_entity_table(dest=TME)
    return {r["CodeEH"]: r for r in csv.DictReader(TME.open(encoding="utf-8-sig"))}


def main():
    rows = list(csv.DictReader(TME.open(encoding="utf-8-sig")))
    table = {r["CodeEH"]: r for r in rows}
    print(f"{len(table)} BDLISA entities loaded\n")

    by_milieu = collections.defaultdict(list)
    for r in rows:
        if r["NiveauEH"] == "3":
            by_milieu[r["MilieuEH"]].append(r["CodeEH"])

    print("one level-3 entity per medium, classified:")
    for milieu in sorted(by_milieu, key=lambda m: (len(m), m)):
        code = by_milieu[milieu][0]
        group, m, entity, note = bdlisa.classify_codes([code], table)
        label = bdlisa.MILIEU_LABELS.get(milieu, "?")
        print(f"  MilieuEH={milieu:<3} {label[:44]:<44} -> {str(group):<9} {note}")

    print("\nedge cases:")
    porous = by_milieu["1"][0]
    karst = by_milieu["3"][0]
    level2 = next(r["CodeEH"] for r in rows if r["NiveauEH"] == "2")
    cases = [
        ("empty list", []),
        ("unknown code", ["ZZZZZZZ"]),
        ("level-2 code only", [level2]),
        ("level-2 + level-3 porous", [level2, porous]),
        ("two level-3, same group", [porous, by_milieu["1"][1]]),
        ("two level-3, porous + karstic", [porous, karst]),
    ]
    for label, codes in cases:
        group, m, entity, note = bdlisa.classify_codes(codes, table)
        print(f"  {label:<30} -> {str(group):<9} {note}")

    print("\nentity totals by group (level 3, metropolitan):")
    met = [r for r in rows if r["NiveauEH"] == "3" and r["CodeEH"][:2] not in ("97", "98")]
    counts = collections.Counter(
        bdlisa.MEDIUM_GROUPS.get(r["MilieuEH"], "unknown") for r in met
    )
    for g, n in counts.most_common():
        print(f"  {g:<10} {n:5}  ({n / len(met):.0%})")

    summary = {
        "source": bdlisa.TME_CSV,
        "nomenclature": "Sandre 353 - Type de milieu pour une entite hydrogeologique",
        "milieu_labels": bdlisa.MILIEU_LABELS,
        "medium_groups": bdlisa.MEDIUM_GROUPS,
        "entities_total": len(rows),
        "entities_by_level": dict(
            sorted(collections.Counter(r["NiveauEH"] for r in rows).items())
        ),
        "milieu_by_level": {
            lvl: dict(
                collections.Counter(
                    r["MilieuEH"] for r in rows if r["NiveauEH"] == lvl
                ).most_common()
            )
            for lvl in sorted({r["NiveauEH"] for r in rows})
        },
        "level3_metropolitan_by_group": dict(counts.most_common()),
        "level3_metropolitan_total": len(met),
    }
    out = DATA / "bdlisa_medium_distribution.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("wrote " + str(out))


if __name__ == "__main__":
    main()
