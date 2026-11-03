"""Shared Hub'Eau API helpers.

Hub'Eau returns at most 20 000 records for page-based pagination, so large
result sets use the `cursor` parameter instead. Both are implemented here;
`paginate` prefers the cursor when the API offers one.
"""
import json
import sys
import time
from pathlib import Path

import requests

BASE = "https://hubeau.eaufrance.fr/api/v1/niveaux_nappes"
DELAY = 0.5  # seconds between paginated calls, per Hub'Eau fair-use guidance
PAGE_SIZE = 5000
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


class HubeauUnreachable(RuntimeError):
    """Raised when the API host cannot be reached at all."""


def get(endpoint, **params):
    """One GET against an endpoint. Returns the decoded JSON body."""
    url = f"{BASE}/{endpoint}"
    try:
        r = requests.get(url, params=params, timeout=180)
    except requests.exceptions.RequestException as exc:
        raise HubeauUnreachable(
            f"Could not reach {url}: {exc}\n"
            "Run scripts/00_check_connectivity.py to diagnose."
        ) from exc
    # 206 = partial content, which Hub'Eau uses for a non-final page.
    if r.status_code not in (200, 206):
        raise RuntimeError(f"HTTP {r.status_code} for {r.url}\n{r.text[:500]}")
    return r.json()


def paginate(endpoint, **params):
    """Yield every record from an endpoint, following cursor or page links."""
    params.setdefault("size", PAGE_SIZE)
    body = get(endpoint, **params)
    total = body.get("count")
    seen = 0
    page = 1
    while True:
        rows = body.get("data") or []
        seen += len(rows)
        print(f"  page {page}: {len(rows)} rows ({seen}/{total})", file=sys.stderr)
        yield from rows

        nxt = body.get("next")
        if not rows or (total is not None and seen >= total) or not nxt:
            break
        page += 1
        time.sleep(DELAY)
        # `next` is a fully-formed URL (cursor or page based); follow it directly.
        r = requests.get(nxt, timeout=180)
        if r.status_code not in (200, 206):
            raise RuntimeError(f"HTTP {r.status_code} following next page: {nxt}")
        body = r.json()


def save_json(obj, name):
    DATA.mkdir(exist_ok=True)
    path = DATA / name
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path} ({path.stat().st_size / 1e6:.2f} MB)")
    return path
