"""BDLISA aquifer-entity reference, from the Sandre open-data mirror.

Hub'Eau station records carry `codes_bdlisa` (a list of BDLISA entity codes),
but no description of the aquifer medium. The medium lives in BDLISA itself, as
the `MilieuEH` attribute of each hydrogeological entity, coded against Sandre
nomenclature 353 ("Type de milieu pour une entite hydrogeologique").

Two things to know about that attribute:

* Nomenclature 353 has 13 values, not 3. Five are mixed double/triple porosity
  classes, and in BDLISA v3 they cover 491 of the 2636 metropolitan level-3
  entities -- too many to ignore. MEDIUM_GROUPS below is the project's grouping
  decision and is the single place to change it.
* Level 1 and 2 entities aggregate several level-3 ones, but they still carry a
  definite medium: code 10 ("Multi-milieux") appears exactly once in the whole
  of BDLISA v3, and code 11 ("Fracture") not at all. So a station that only
  references a level-1/2 entity can still be grouped, just more coarsely --
  classify_codes marks those `level2_only` so they can be excluded later.

Sources, both on services.sandre.eaufrance.fr (bdlisa.eaufrance.fr and
infoterre.brgm.fr serve the same data but are often unreachable):
  TME.csv            -- the entity attribute table, 0.5 MB, no geometry
  EntiteHydroGeol_FXX.gpkg -- polygons for the spatial fallback, 114 MB
"""
import csv
import io
import json
import time
from pathlib import Path

import requests

SANDRE_DL = "https://services.sandre.eaufrance.fr/telechargement/geo/SAQ/BDLISA/3/"
TME_CSV = SANDRE_DL + "BDLISA_V3/CSV/TME.csv"
GPKG_FXX = SANDRE_DL + "EntiteHydroGeol/GPKG/EntiteHydroGeol_FXX.gpkg"
NSA_353 = "https://api.sandre.eaufrance.fr/referentiels/v1/nsa/353.json"

# Fallback for the attribute table: the same layer over WFS. Slower, and
# PROPERTYNAME does not drop geometry, so this pulls ~240 MB. Prefer TME.csv.
WFS = "https://services.sandre.eaufrance.fr/geo/sandre"
LAYER = "sa:EntiteHydroGeol_FXX"

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ATTRS = "CodeEH,LibelleEH,NiveauEH,InclusEH,EtatEH,NatureEH,MilieuEH,ThemeEH"

# Sandre nomenclature 353, fetched 2026-11-03. Kept here so the pipeline is
# reproducible offline; refresh_nomenclature() re-fetches and verifies it.
MILIEU_LABELS = {
    "X": "Sans objet",
    "0": "Inconnu",
    "1": "Milieu poreux",
    "2": "Milieu fissure",
    "3": "Milieu karstique",
    "4": "Double porosite : matricielle et de fissures",
    "5": "Double porosite : karstique et de fissures",
    "6": "Double porosite : de fractures et/ou de fissures",
    "7": "Double porosite : matricielle et de fractures",
    "8": "Double porosite : matricielle et karstique",
    "9": "Triple porosite : matricielle, de fractures et karstique",
    "10": "Multi-milieux",
    "11": "Fracture",
}

# The poster compares three media. Only the unambiguous classes are used:
#   porous   <- 1
#   fissured <- 2 (fissured), 11 (fractured), 6 (fracture/fissure double porosity)
#   karstic  <- 3
# Mixed classes that combine a matrix or karst with something else (4, 5, 7, 8,
# 9) are deliberately NOT assigned: a station in a matrix-and-karst entity cannot
# be used to characterise either medium's drought response. They are 19% of
# metropolitan level-3 entities, so this exclusion is the main cost of the
# three-way design and belongs in the poster's limitations.
MEDIUM_GROUPS = {
    "1": "porous",
    "2": "fissured",
    "11": "fissured",
    "6": "fissured",
    "3": "karstic",
    "4": "mixed",
    "5": "mixed",
    "7": "mixed",
    "8": "mixed",
    "9": "mixed",
    "0": "unknown",
    "X": "unknown",
    "10": "unknown",
}
POSTER_GROUPS = ("porous", "fissured", "karstic")


def refresh_nomenclature():
    """Re-fetch Sandre nomenclature 353 and return {code: label}."""
    body = requests.get(NSA_353, timeout=120).json()
    ref = body["REFERENTIELS"]["Referentiel"][0]
    return {e["CdElement"]: e["LbElement"] for e in ref["Element"]}


def fetch_entity_table(dest=None, timeout=300):
    """Download TME.csv and return {CodeEH: attributes}.

    TME.csv is the whole BDLISA v3 entity table for France including the
    overseas departments: 3903 rows, of which 2750 are level 3.
    """
    print(f"GET {TME_CSV} ...")
    t0 = time.time()
    r = requests.get(TME_CSV, timeout=timeout)
    r.raise_for_status()
    print(f"  {len(r.content) / 1e6:.2f} MB in {time.time() - t0:.0f}s")
    if dest:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        print(f"  saved {dest}")
    text = r.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    return {row["CodeEH"]: row for row in rows if row.get("CodeEH")}


def fetch_polygons(dest, timeout=1800):
    """Download the metropolitan entity polygons (114 MB) for the spatial join."""
    dest = Path(dest)
    if dest.exists():
        print(f"using cached {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"GET {GPKG_FXX} (114 MB) ...")
    t0 = time.time()
    with requests.get(GPKG_FXX, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    print(f"  saved {dest} in {time.time() - t0:.0f}s")
    return dest


def classify_codes(codes_bdlisa, table):
    """Map a station's `codes_bdlisa` list to a poster group.

    Returns (group, medium_code, entity_code, note). Level-3 entities are
    preferred, being the finest classification available; a level-1/2 code is
    used only when no level-3 code is present, and is flagged `level2_only`.
    If several level-3 entities disagree the station is ambiguous and is
    dropped rather than forced into a group.
    """
    codes = [c for c in (codes_bdlisa or []) if c in table]
    if not codes:
        return None, None, None, "no_bdlisa_code_in_reference"

    by_level = sorted(codes, key=lambda c: -int(table[c].get("NiveauEH") or 0))
    level3 = [c for c in by_level if str(table[c].get("NiveauEH")) == "3"]
    candidates = level3 or by_level

    groups = {}
    for c in candidates:
        milieu = str(table[c].get("MilieuEH"))
        groups.setdefault(MEDIUM_GROUPS.get(milieu, "unknown"), (milieu, c))

    usable = {g: v for g, v in groups.items() if g in POSTER_GROUPS}
    if len(usable) == 1:
        group, (milieu, code) = next(iter(usable.items()))
        note = "level3" if level3 else f"level{table[code].get('NiveauEH')}_only"
        return group, milieu, code, note
    if len(usable) > 1:
        return None, None, candidates[0], "ambiguous_" + "+".join(sorted(usable))
    milieu, code = next(iter(groups.values()))
    return None, milieu, code, f"milieu_{milieu}_not_in_poster_groups"
