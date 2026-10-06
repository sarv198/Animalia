"""Compare data/curated/fossil_dates.csv with the Paleobiology Database (PBDB).

A review aid, not a pipeline step. For every curated row with a pbdb_name it
pulls PBDB body-fossil occurrences identified with confidence to genus or
better (footprints and uncertain IDs excluded), then prints PBDB's oldest and
youngest occurrence next to the curated value, naming the fossil responsible.
Differences are expected where the curated note explains them (misdated or
misassigned PBDB records); anything unexplained is worth a closer look.

Usage:  python scripts/review_fossil_dates.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.config import FOSSIL_DATES_PATH

PBDB_OCCS_URL = "https://paleobiodb.org/data1.2/occs/list.json"


def fetch_occurrences(name: str) -> list[dict[str, Any]]:
    resp = requests.get(
        PBDB_OCCS_URL,
        params={
            "base_name": name,
            "pres": "regular",        # body fossils only: no ichnotaxa or form taxa
            "idqual": "certain",      # no 'cf.', 'aff.', '?'
            "taxon_reso": "genus",    # identified to genus or species
            "limit": "all",
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json().get("records", [])


def extremes(records: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The occurrence that could be oldest (greatest early age) and the one that
    could be youngest (smallest late age)."""
    if not records:
        return None, None
    oldest = max(records, key=lambda r: float(r["eag"]))
    youngest = min(records, key=lambda r: float(r["lag"]))
    return oldest, youngest


def _describe(record: dict[str, Any] | None) -> str:
    if record is None:
        return "no records"
    return f"{record.get('tna')} ({record.get('oei')}, {record['eag']}-{record['lag']} Ma)"


def consistent(curated: float | None, record: dict[str, Any] | None) -> bool:
    """A curated date agrees with PBDB if it lies within that fossil's dating
    interval [late age, early age]; fossils are dated to intervals, not points."""
    if curated is None or record is None:
        return True
    return float(record["lag"]) - 0.1 <= curated <= float(record["eag"]) + 0.1


def _flag(curated: float | None, record: dict[str, Any] | None) -> str:
    return "" if consistent(curated, record) else "  <-- outside PBDB interval"


def main() -> None:
    with FOSSIL_DATES_PATH.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        name, pbdb_name = row["name"], (row["pbdb_name"] or "").strip()
        if not pbdb_name:
            continue
        oldest, youngest = extremes(fetch_occurrences(pbdb_name))
        curated_old = float(row["node_min_age_ma"] or row["first_appearance_ma"] or "nan")
        curated_young = float(row["last_appearance_ma"]) if row["last_appearance_ma"] else None
        print(f"== {name} (PBDB: {pbdb_name})")
        print(f"   curated oldest  {curated_old:7.1f} Ma | PBDB oldest   {_describe(oldest)}"
              f"{_flag(curated_old, oldest)}")
        if curated_young is not None:
            print(f"   curated last    {curated_young:7.1f} Ma | PBDB youngest {_describe(youngest)}"
                  f"{_flag(curated_young, youngest)}")
        print(f"   note: {row['note']}")


if __name__ == "__main__":
    main()
