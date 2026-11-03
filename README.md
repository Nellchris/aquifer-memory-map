# Aquifer Memory Map

Scientific poster on how French aquifer types (porous, fissured, karstic)
recovered from the 2022 European drought, from Hub'Eau piezometry and the
BDLISA aquifer classification.

## Status: gate check GO

Station counts are in, from a Hub'Eau fetch run in Google Colab
(`scripts/colab_fetch_stations.py`) because Hub'Eau is unreachable from this
machine. 7080 stations with >= 120 measurements; after the BDLISA join and an
approximate date filter:

| Group | With BDLISA | Record filter | Final |
|---|---|---|---|
| porous | 2873 | 2272 | 970 |
| fissured | 657 | 548 | 332 |
| karstic | 219 | 141 | **105** |

**GO** — all three groups are far above the 25-station threshold. Karstic is the
binding group, as the entity-level distribution predicted, but with 105 stations
it has ample headroom.

The date filter is approximate: it uses the station metadata's first and last
measurement dates, so it says nothing about gaps inside the window.
`04_drought_filter.py` does the real gap check on the time series.

Run `python scripts/00_check_connectivity.py` to see whether Hub'Eau is
reachable before trying anything that calls it directly from here.

### What is blocked

| Host | DNS | TCP 443 | TLS |
|---|---|---|---|
| `hubeau.eaufrance.fr` | 217.108.210.220 | connects | **handshake reset** |
| `bdlisa.eaufrance.fr` | 217.108.210.220 | connects | **handshake reset** |
| `www.brgm.fr`, `infoterre.brgm.fr`, `ades.eaufrance.fr` | 193.56.4.x | **refused** | - |
| `services.sandre.eaufrance.fr`, `api.sandre.eaufrance.fr` | 195.220.97.x | connects | OK |
| `www.data.gouv.fr` (control) | 37.59.183.x | connects | OK |

The reset arrives immediately after the TLS ClientHello, on every client tried
(Python/OpenSSL, curl/schannel, the Chromium-based browser pane, and a
server-side fetch), at both TLS 1.2 and 1.3, with and without ALPN. Plain HTTP
to port 80 succeeds and returns the normal 301 to HTTPS, so the host is up and
routable; it is the TLS session that is being killed. Two different IP ranges
are affected while a third French government host on a third range works, so
this is name-based (SNI) filtering between this machine and BRGM, not an API
outage and not something the scripts can route around.

Things to try, roughly in order:

1. Turn off HTTPS/SSL inspection in any local antivirus or endpoint security.
2. Allow `*.eaufrance.fr` and `*.brgm.fr` on the network firewall.
3. Run from another network, or over a VPN.
4. Confirm the API itself is healthy at
   <https://api.gouv.fr/les-api/api_hubeau_piezometrie>.

There is no usable mirror. The data.gouv.fr catalogue entries for piezometry
are link-only records pointing back at the same blocked hosts.

## What is done and verified

The BDLISA half of the pipeline is finished, because BDLISA is also published
through Sandre, which is reachable.

**The aquifer medium is not on the station record.** Hub'Eau station responses
carry `codes_bdlisa` (a list of BDLISA entity codes) and `urns_bdlisa`, but no
medium. The medium is the `MilieuEH` attribute of the BDLISA entity, coded
against Sandre nomenclature 353. So the join is
`station.codes_bdlisa` -> `BDLISA.CodeEH` -> `MilieuEH` -> group; no shapefile
or spatial join is needed for stations that carry a code.

**Nomenclature 353 has 13 values, not 3.** Fetched live from
`api.sandre.eaufrance.fr/referentiels/v1/nsa/353.json`:

| Code | Label | Group used here |
|---|---|---|
| 1 | Milieu poreux | porous |
| 2 | Milieu fissure | fissured |
| 3 | Milieu karstique | karstic |
| 6 | Double porosite : de fractures et/ou de fissures | fissured |
| 4, 5, 7, 8, 9 | double/triple porosity combinations | **excluded (mixed)** |
| 0, X, 10, 11 | Inconnu, Sans objet, Multi-milieux, Fracture | excluded (unknown) |

Codes 4, 5, 7, 8 and 9 mix a matrix or a karst network with something else. A
station in a matrix-and-karst entity cannot characterise either medium's
drought response, so they are not assigned to a group. That exclusion is the
main methodological cost of the three-way design and belongs in the poster's
limitations.

**Entity-level distribution** (BDLISA v3, 2636 metropolitan level-3 entities)
— the denominator the station counts should be read against:

| Group | Entities | Share |
|---|---|---|
| fissured | 902 | 34% |
| porous | 893 | 34% |
| mixed (excluded) | 491 | 19% |
| karstic | 347 | 13% |
| unknown | 3 | 0% |

Karstic is the scarce group at entity level, so it is the one most likely to
fail the gate. Two further findings: `MilieuEH` 10 ("Multi-milieux") appears
exactly once in all of BDLISA v3 and 11 ("Fracture") not at all, so level-1 and
level-2 entities do carry a definite medium and a station referencing only a
coarse entity can still be grouped — `classify_codes` flags those `level2_only`
so they can be excluded later if the poster requires level-3 precision.

Two independent Sandre routes were checked against each other and agree
field-for-field on the sample obtained before the bulk request timed out.

## Data sources

| What | Where | Size |
|---|---|---|
| Entity attribute table | `.../BDLISA/3/BDLISA_V3/CSV/TME.csv` | 0.5 MB |
| Entity polygons (spatial fallback) | `.../BDLISA/3/EntiteHydroGeol/GPKG/EntiteHydroGeol_FXX.gpkg` | 114 MB |
| Medium nomenclature | `api.sandre.eaufrance.fr/referentiels/v1/nsa/353.json` | 5 KB |

all under `https://services.sandre.eaufrance.fr/telechargement/geo/SAQ/`.

`TME.csv` is the whole v3 entity table (3903 rows: 187 level-1, 966 level-2,
2750 level-3) with no geometry. The same layer is also served as WFS
`sa:EntiteHydroGeol_FXX` from `services.sandre.eaufrance.fr/geo/sandre`, but
`PROPERTYNAME` there does not drop geometry, which makes an attributes-only
request about 240 MB — it timed out. Use the CSV.

## Scripts

Numbered scripts form the pipeline; run them in order.

| Script | Needs Hub'Eau | Does |
|---|---|---|
| `00_check_connectivity.py` | no | reachability, separating DNS / TCP / TLS failure |
| `01_explore_api.py` | **yes** | dumps the live station and chronique schema to `data/api_schema.json` |
| `02_fetch_stations.py` | **yes** | all stations with `nb_mesures_piezo_min=120` -> `data/stations_raw.json` |
| `03_classify_bdlisa.py` | no (needs 02's output) | code join, then spatial fallback -> `data/stations_classified.csv` |
| `03a_bdlisa_check.py` | no | verifies the join logic, writes `data/bdlisa_medium_distribution.json` |
| `04_drought_filter.py` | **yes** | drought-window coverage per group, prints the gate table -> `data/station_counts.json` |

`hubeau.py` and `bdlisa.py` are the shared modules. `bdlisa.MEDIUM_GROUPS` is
the single place the grouping decision lives.

`03a_bdlisa_check.py` runs today and passes. Under the block, `01` and `02`
exit 2 with the failing URL and a pointer to `00`; `03` and `04` exit 1 naming
the upstream output they are missing. Verified: no script fails silently.

### Run order once Hub'Eau is reachable

```
python scripts/00_check_connectivity.py
python scripts/01_explore_api.py        # check field names before trusting 02-04
python scripts/02_fetch_stations.py
python scripts/03_classify_bdlisa.py
python scripts/04_drought_filter.py     # prints the GATE CHECK table
```

Check `data/api_schema.json` against the field names `02`-`04` use
(`codes_bdlisa`, `nb_mesures_piezo`, `date_debut_mesure`, `date_fin_mesure`,
`lat`/`lon`, `date_mesure`). Those come from the API documentation and from the
R and Python client packages, not from a live response, so they are the most
likely thing to need a fix. `02` and `03` degrade loudly rather than silently if
a name is wrong.

## Filter parameters

- record length: `nb_mesures_piezo_min=120` (~10 years of monthly data)
- drought window: 2022-06-01 to 2025-12-31
- maximum gap inside the window: 62 days
- gate: GO if every group >= 25, WATCH at 20-24, NO-GO below 20

`04` tests a 20-station sample per group (seed 20220601) and extrapolates the
pass rate to the full group, so its drought column is an estimate; the sample
size and seed are recorded in `data/station_counts.json`.

## Licence

BDLISA and Hub'Eau data are published by BRGM / Eaufrance under the Licence
Ouverte (Etalab).
