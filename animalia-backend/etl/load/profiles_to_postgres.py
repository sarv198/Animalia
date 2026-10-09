"""Load family profiles (species counts, range maps) and Wikipedia summaries.

Both tables are replaced wholesale on each run, so reruns are idempotent and
names that leave the tree leave the tables too. When the GARD ranges were not
built this run (shapefile not downloaded), ranges already in the database are
kept rather than wiped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.database import SessionLocal
from app.models import FamilyProfile, TaxonSummary
from etl.transform import ranges as gard


@dataclass
class ProfileLoadStats:
    families: int = 0
    families_with_range: int = 0
    families_with_rep_range_only: int = 0
    summaries: int = 0
    names_without_summary: int = 0


def load(
    species_counts: dict[str, int],
    checklist_release: str | None,
    family_ranges: dict[str, gard.FamilyRange] | None,
    summaries: dict[str, dict[str, Any] | None],
) -> ProfileLoadStats:
    stats = ProfileLoadStats()
    db = SessionLocal()
    try:
        previous = {p.family: p for p in db.query(FamilyProfile).all()}
        db.query(FamilyProfile).delete()
        for family, count in sorted(species_counts.items()):
            profile = FamilyProfile(family=family, species_count=count, checklist_release=checklist_release)
            fr = family_ranges.get(family) if family_ranges is not None else None
            old = previous.get(family) if family_ranges is None else None
            if fr is not None:
                profile.range_geojson = fr.range_geojson
                profile.range_species_mapped = fr.species_mapped
                profile.rep_scientific_name = fr.rep_scientific_name
                profile.rep_range_geojson = fr.rep_range_geojson
                profile.range_source = gard.SOURCE
                profile.range_citation = gard.CITATION
            elif old is not None:  # GARD not rebuilt this run: keep what was loaded
                for column in (
                    "range_geojson", "range_species_mapped", "rep_scientific_name",
                    "rep_range_geojson", "range_source", "range_citation",
                ):
                    setattr(profile, column, getattr(old, column))
            db.add(profile)
            stats.families += 1
            if profile.range_geojson:
                stats.families_with_range += 1
            elif profile.rep_range_geojson:
                stats.families_with_rep_range_only += 1

        db.query(TaxonSummary).delete()
        for name, summary in sorted(summaries.items()):
            if not summary:
                stats.names_without_summary += 1
                continue
            where = summary.get("range") or {}
            db.add(TaxonSummary(
                name=name,
                **{k: summary[k] for k in ("title", "url", "extract", "revision", "licence", "licence_url")},
                range_text=where.get("text"),
                range_scope=where.get("scope"),
                range_title=where.get("title"),
                range_url=where.get("url"),
            ))
            stats.summaries += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return stats


def print_stats(stats: ProfileLoadStats) -> None:
    print(
        f"family profiles: {stats.families} families, {stats.families_with_range} with a GARD family range, "
        f"{stats.families_with_rep_range_only} with only the representative's range"
    )
    print(f"Wikipedia summaries: {stats.summaries} loaded, {stats.names_without_summary} names without one")
