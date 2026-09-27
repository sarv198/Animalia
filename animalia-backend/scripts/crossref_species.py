"""
crossref_species.py

Takes the curated reptile species CSV (one row per family) and cross-references
each species against four taxonomic/conservation data sources:

  - GBIF          (backbone taxon key)          - no auth needed
  - Catalogue of Life / ChecklistBank (taxon id) - no auth needed
  - IUCN Red List (conservation status)          - free API token required
  - Open Tree of Life (phylogeny node / OTT id)  - no auth needed

Output: a CSV with one row per species, containing every ID we found plus a
`review_flag` column marking anything that didn't match cleanly and should be
checked by a human before it goes into the pipeline.

Usage:
    export IUCN_API_TOKEN="your-token-here"   # https://api.iucnredlist.org/
    python scripts/crossref_species.py --in data/curated/reptile_family_representatives.csv --out data/processed/species_crossref.csv
"""

import argparse
import csv
import os
import time

import requests

GBIF_MATCH_URL = "https://api.gbif.org/v1/species/match"
COL_SEARCH_URL = "https://api.catalogueoflife.org/dataset/3LR/nameusage/search"
IUCN_BASE_URL = "https://api.iucnredlist.org/api/v4"
OPENTREE_MATCH_URL = "https://api.opentreeoflife.org/v3/tnrs/match_names"

REQUEST_TIMEOUT = 15
SLEEP_BETWEEN_CALLS = 0.3  # be polite to free public APIs


def load_species_list(path):
    """Read the curated CSV and return a list of dicts."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def match_gbif(species_name):
    """
    Match a scientific name against the GBIF backbone taxonomy.
    Returns the usageKey (GBIF's taxon id), match type, and confidence score,
    which together tell you how much to trust the match.
    """
    try:
        resp = requests.get(
            GBIF_MATCH_URL,
            params={"name": species_name, "strict": "false"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "gbif_usage_key": data.get("usageKey"),
            "gbif_matched_name": data.get("scientificName"),
            "gbif_match_type": data.get("matchType"),  # EXACT, FUZZY, NONE...
            "gbif_confidence": data.get("confidence"),
            "gbif_status": data.get("status"),  # ACCEPTED, SYNONYM...
        }
    except requests.RequestException as e:
        return {"gbif_error": str(e)}


def match_col(species_name):
    """
    Search Catalogue of Life (via ChecklistBank) for the species and return
    the accepted taxon id. '3LR' is ChecklistBank's alias for whatever the
    current CoL annual release is, so you don't have to hardcode a version.
    """
    try:
        resp = requests.get(
            COL_SEARCH_URL,
            params={
                "q": species_name,
                "rank": "species",
                "status": "accepted",
                "limit": 1,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("result", [])
        if not results:
            return {"col_taxon_id": None, "col_match": "NO_MATCH"}
        top = results[0]
        usage = top.get("usage", top)  # response shape varies slightly by version
        return {
            "col_taxon_id": usage.get("id"),
            "col_matched_name": usage.get("name", {}).get("scientificName")
            if isinstance(usage.get("name"), dict)
            else None,
            "col_match": "OK",
        }
    except requests.RequestException as e:
        return {"col_error": str(e)}


def match_iucn(genus, species_epithet, token):
    """
    Look up conservation status on the IUCN Red List.
    Requires a free API token - register at https://api.iucnredlist.org/
    and pass it in via the IUCN_API_TOKEN environment variable.
    """
    if not token:
        return {"iucn_status": None, "iucn_error": "no token provided"}
    try:
        resp = requests.get(
            f"{IUCN_BASE_URL}/taxa/scientific_name",
            params={"genus_name": genus, "species_name": species_epithet},
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        # The v4 API nests the current assessment info - adjust this parsing
        # if IUCN changes their response shape; print(data) once to confirm.
        assessments = data.get("assessments") or data.get("result") or []
        if not assessments:
            return {
                "iucn_status": None,
                "iucn_taxon_id": data.get("taxon", {}).get("sis_taxon_id"),
            }
        latest = assessments[0]
        return {
            "iucn_taxon_id": data.get("taxon", {}).get("sis_taxon_id"),
            "iucn_status": latest.get("red_list_category_code")
            or latest.get("category"),
            "iucn_year": latest.get("year_published"),
        }
    except requests.RequestException as e:
        return {"iucn_error": str(e)}


def match_opentree_batch(species_names):
    """
    Open Tree of Life supports batching, so we send all species names in a
    single request instead of one call per species. Returns a dict mapping
    the original name -> OTT id (or None if unmatched).
    """
    try:
        resp = requests.post(
            OPENTREE_MATCH_URL,
            json={"names": species_names, "do_approximate_matching": True},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        results = {}
        for match in data.get("results", []):
            queried_name = match.get("name")
            candidates = match.get("matches", [])
            if candidates:
                best = candidates[0]
                results[queried_name] = {
                    "ott_id": best.get("taxon", {}).get("ott_id"),
                    "ott_matched_name": best.get("taxon", {}).get("name"),
                    "ott_score": best.get("score"),
                }
            else:
                results[queried_name] = {"ott_id": None}
        return results
    except requests.RequestException as e:
        print(f"OpenTree batch match failed: {e}")
        return {}


def flag_for_review(row):
    """
    Decide whether a row needs a human to double-check it before it's trusted.
    Anything that didn't match cleanly across sources gets flagged rather than
    silently accepted - a wrong match here corrupts a leaf of the final tree.
    """
    reasons = []
    if row.get("gbif_match_type") not in ("EXACT",):
        reasons.append("gbif_not_exact")
    if row.get("col_match") != "OK":
        reasons.append("col_no_match")
    if not row.get("ott_id"):
        reasons.append("opentree_no_match")
    if not row.get("iucn_status"):
        reasons.append("iucn_no_status")
    return ";".join(reasons) if reasons else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in",
        dest="input_path",
        default="data/curated/reptile_family_representatives.csv",
    )
    parser.add_argument(
        "--out", dest="output_path", default="data/processed/species_crossref.csv"
    )
    args = parser.parse_args()

    species_rows = load_species_list(args.input_path)
    iucn_token = os.environ.get("IUCN_API_TOKEN", "")
    if not iucn_token:
        print("Warning: IUCN_API_TOKEN not set - conservation status will be blank.")

    all_names = [row["species"] for row in species_rows]
    print(f"Batch-matching {len(all_names)} names against Open Tree of Life...")
    opentree_results = match_opentree_batch(all_names)

    enriched_rows = []
    for i, row in enumerate(species_rows, start=1):
        name = row["species"]
        print(f"[{i}/{len(species_rows)}] {name}")

        genus, _, epithet = name.partition(" ")

        gbif_data = match_gbif(name)
        time.sleep(SLEEP_BETWEEN_CALLS)

        col_data = match_col(name)
        time.sleep(SLEEP_BETWEEN_CALLS)

        iucn_data = match_iucn(genus, epithet, iucn_token)
        time.sleep(SLEEP_BETWEEN_CALLS)

        ott_data = opentree_results.get(name, {"ott_id": None})

        merged = {**row, **gbif_data, **col_data, **iucn_data, **ott_data}
        merged["review_flag"] = flag_for_review(merged)
        enriched_rows.append(merged)

    fieldnames = list(enriched_rows[0].keys())
    os.makedirs(os.path.dirname(args.output_path) or ".", exist_ok=True)
    with open(args.output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    flagged = sum(1 for r in enriched_rows if r["review_flag"])
    print(f"\nDone. Wrote {len(enriched_rows)} rows to {args.output_path}.")
    print(f"{flagged} rows flagged for manual review.")


if __name__ == "__main__":
    main()
