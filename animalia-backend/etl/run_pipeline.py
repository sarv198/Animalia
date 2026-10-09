"""Load species_crossref.csv, build and date the phylogeny, then run data-quality checks.

Steps:
  1. species + classification   (species_crossref.csv -> taxa, species)
  2. Open Tree extract          (network; cached in data/raw/opentree/, only
                                 fetched when missing or with --refresh-opentree)
  3. family check               (every species of each family, from The Reptile
                                 Database, located in Open Tree's tree)
  4. phylogeny                  (Open Tree subtree + curated backbone)
  5. dating                     (TimeTree 5, cached in data/raw/timetree/, plus
                                 data/curated/fossil_dates.csv)
  6. load                       (-> phylo_nodes, phylogeny_edges)
  7. media                      (images from Wikimedia Commons + GBIF, IUCN
                                 status from Wikipedia; cached in data/raw/media/)
  8. profiles                   (species counts from The Reptile Database,
                                 family range maps from GARD 1.7 when its
                                 shapefile is in data/raw/gard/, and Wikipedia
                                 summaries cached in data/raw/media/)
  9. validation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.config import OPENTREE_RAW_DIR
import requests

from etl.extract import media, opentree, reptiledb, summaries
from etl.extract.timetree import TimeTreeClient
from etl.load.phylogeny_to_postgres import load as load_phylogeny
from etl.load.media_to_postgres import load as load_media
from etl.load.media_to_postgres import print_stats as print_media_stats
from etl.load.phylogeny_to_postgres import print_stats as print_phylogeny_stats
from etl.load.profiles_to_postgres import load as load_profiles
from etl.load.profiles_to_postgres import print_stats as print_profile_stats
from etl.load.to_postgres import load, print_stats
from etl.transform import build_phylogeny, date_phylogeny, family_check, ranges
from etl.validate.checks import ValidationError, run as run_checks

DEFAULT_CSV = ROOT / "species_crossref.csv"


def print_dating_report(report: date_phylogeny.DatingReport, client: TimeTreeClient) -> None:
    print("node ages by source: " + ", ".join(f"{k}={v}" for k, v in sorted(report.by_source.items())))
    print(f"TimeTree queries: {report.timetree_queries} ({client.network_calls} over the network)")
    for name, age in report.discarded:
        print(f"  discarded weaker TimeTree estimate: {name} ({age:.1f} Ma)")
    for name, before, after in report.adjusted:
        print(f"  raised for consistency: {name} {before:.1f} -> {after:.1f} Ma")
    if report.interpolated:
        print(f"  interpolated (no usable TimeTree estimate): {', '.join(report.interpolated)}")


def print_family_report(checks: dict[str, family_check.FamilyCheck]) -> None:
    counts: dict[str, int] = {}
    for check in checks.values():
        counts[check.status] = counts.get(check.status, 0) + 1
    print("family check: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    overridden = sorted(f for f, c in checks.items() if c.override)
    if overridden:
        print(f"  status set by hand (family_status_overrides.csv): {', '.join(overridden)}")
    outside = sorted(f for f, c in checks.items() if c.representative_in_main_branch is False)
    taxonomy_only = sorted(f for f, c in checks.items() if c.representative_trees == 0)
    if outside:
        print(f"  representative outside its family's main branch (swap it): {', '.join(outside)}")
    if taxonomy_only:
        print(f"  representative placed by taxonomy only (consider swapping): {', '.join(taxonomy_only)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", nargs="?", default=str(DEFAULT_CSV))
    parser.add_argument(
        "--refresh-opentree",
        action="store_true",
        help="re-download Open Tree data even if a cached extract exists",
    )
    parser.add_argument(
        "--refresh-media",
        action="store_true",
        help="re-fetch images, Wikipedia IUCN status and Wikipedia summaries",
    )
    parser.add_argument(
        "--refresh-timetree",
        action="store_true",
        help="re-query TimeTree for every split instead of using cached answers",
    )
    args = parser.parse_args()
    csv_path = Path(args.csv_path)

    stats = load(csv_path)
    print_stats(stats)

    if args.refresh_opentree or not opentree.cache_complete():
        opentree.extract(csv_path)
    else:
        print(f"using cached Open Tree extract in {OPENTREE_RAW_DIR}")

    placement, checks, stale_overrides = family_check.run(csv_path)
    print_family_report(checks)
    if stale_overrides:
        print(f"  hand-set statuses no longer needed: {', '.join(stale_overrides)}")

    build = build_phylogeny.run(csv_path, placement)
    print(f"Open Tree synthesis: {build.synth_id}")

    client = TimeTreeClient(refresh=args.refresh_timetree)
    try:
        report = date_phylogeny.run(build, client)
    finally:
        client.save()  # keep whatever was fetched, even if dating fails
    print_dating_report(report, client)
    versions = client.versions()
    timetree_version = ",".join(sorted(versions)) or None
    print(f"TimeTree data version: {timetree_version}")

    print_phylogeny_stats(load_phylogeny(build, timetree_version=timetree_version))

    rows = opentree.read_crossref(csv_path)
    try:
        species_media = media.extract(rows, refresh=args.refresh_media)
    except requests.RequestException as exc:  # enrichment only: keep going
        print(f"media fetch failed ({exc}); loading what is cached")
        species_media = media.cached(rows)
    print_media_stats(load_media(species_media), len(rows))

    checklist_path = reptiledb.checklist_path()
    checklist = reptiledb.read_checklist(checklist_path)
    species_family = {ranges.normalise(s): f for s, f in zip(checklist["species"], checklist["family"])}
    representatives = {row["family"].strip(): row["species"].strip() for row in rows}
    family_ranges = ranges.run(sorted(checks), species_family, representatives)
    names = sorted({r.family or r.label for r in build.records if r.family or r.label})
    try:
        species_articles = {
            row["family"].strip(): (wiki["title"], wiki["url"])
            for row in rows
            if (wiki := (species_media.get(row["species"].strip()) or {}).get("wikipedia"))
        }
        taxon_summaries = summaries.extract(names, refresh=args.refresh_media, species_articles=species_articles)
    except requests.RequestException as exc:  # enrichment only: keep going
        print(f"summary fetch failed ({exc}); loading what is cached")
        cache = summaries.cached()
        taxon_summaries = {name: cache.get(name) for name in names}
    print_profile_stats(load_profiles(
        {fam: check.checklist_species for fam, check in checks.items()},
        reptiledb.release_of(checklist_path.name),
        family_ranges,
        taxon_summaries,
    ))

    try:
        run_checks()
    except ValidationError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("all checks passed")


if __name__ == "__main__":
    main()
