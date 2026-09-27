"""Load species_crossref.csv into Postgres.

Uses the ORM models in app.models and SessionLocal from app.database.
Does not define tables of its own.

Hierarchy per row:
  clade_group (rank=clade)
    -> family (rank=family)
      -> species taxon (rank=species)
        -> species row (enrichment / external ids)
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import Source, Species, Taxon

SOURCE_NAME = "species_crossref"
RANK_CLADE = "clade"
RANK_FAMILY = "family"
RANK_SPECIES = "species"


@dataclass
class LoadStats:
    taxa_inserted: int = 0
    taxa_updated: int = 0
    species_inserted: int = 0
    species_updated: int = 0
    flagged: int = 0


def blank_to_none(value: str | None) -> str | None:
    """CSV empty cells are null, not the string ''."""
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    return text


def to_int(value: str | None) -> int | None:
    text = blank_to_none(value)
    if text is None:
        return None
    return int(float(text))


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def get_or_create_taxon(
    cache: dict[tuple[str, str], Taxon],
    db,
    stats: LoadStats,
    scientific_name: str,
    rank: str,
    parent: Taxon | None,
) -> Taxon:
    """Look up a taxon by (scientific_name, rank) in the in-memory cache.

    The cache is preloaded from the database once. This helper never queries.
    """
    key = (scientific_name, rank)
    existing = cache.get(key)
    if existing is not None:
        return existing

    taxon = Taxon(
        scientific_name=scientific_name,
        rank=rank,
        parent=parent,
        taxonomic_source=SOURCE_NAME,
    )
    db.add(taxon)
    cache[key] = taxon
    stats.taxa_inserted += 1
    return taxon


def apply_species_fields(species: Species, row: dict[str, str], taxon: Taxon) -> None:
    """Map CSV columns onto the species row. Empty cells become NULL."""
    species.taxon = taxon
    species.common_name = blank_to_none(row.get("common_name"))
    species.col_taxon_id = blank_to_none(row.get("col_taxon_id"))
    species.gbif_taxon_id = to_int(row.get("gbif_usage_key"))
    species.ott_id = to_int(row.get("ott_id"))
    species.iucn_category = blank_to_none(row.get("iucn_status"))
    species.iucn_assessment_year = to_int(row.get("iucn_year"))


def ensure_source(db, csv_path: Path) -> None:
    existing = (
        db.query(Source).filter(Source.source_name == SOURCE_NAME).first()
    )
    if existing is not None:
        return
    db.add(
        Source(
            source_name=SOURCE_NAME,
            source_version="reptile family representatives",
            source_url=str(csv_path),
        )
    )
    db.flush()


def load(csv_path: Path) -> LoadStats:
    """Load the crossref CSV in one transaction. Roll back on any error."""
    rows = load_rows(csv_path)
    stats = LoadStats()
    db = SessionLocal()
    try:
        taxa_cache: dict[tuple[str, str], Taxon] = {
            (taxon.scientific_name, taxon.rank): taxon
            for taxon in db.query(Taxon).all()
        }
        species_cache: dict[str, Species] = {
            species.scientific_name: species
            for species in db.query(Species).all()
        }

        ensure_source(db, csv_path)

        for row in rows:
            clade_name = blank_to_none(row.get("clade_group"))
            family_name = blank_to_none(row.get("family"))
            species_name = blank_to_none(row.get("species"))
            if not clade_name or not family_name or not species_name:
                raise ValueError(
                    "Row is missing clade_group, family, or species: "
                    f"{clade_name!r} / {family_name!r} / {species_name!r}"
                )

            clade = get_or_create_taxon(
                taxa_cache, db, stats, clade_name, RANK_CLADE, None
            )
            family = get_or_create_taxon(
                taxa_cache, db, stats, family_name, RANK_FAMILY, clade
            )
            # The species node's parent is its family; the family's parent is
            # its clade. Species.taxon points at that species node.
            species_taxon = get_or_create_taxon(
                taxa_cache, db, stats, species_name, RANK_SPECIES, family
            )

            existing = species_cache.get(species_name)
            if existing is None:
                species = Species(scientific_name=species_name)
                apply_species_fields(species, row, species_taxon)
                db.add(species)
                species_cache[species_name] = species
                stats.species_inserted += 1
            else:
                apply_species_fields(existing, row, species_taxon)
                stats.species_updated += 1

            if blank_to_none(row.get("review_flag")) is not None:
                stats.flagged += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return stats


def print_stats(stats: LoadStats) -> None:
    print(f"taxa inserted: {stats.taxa_inserted}")
    print(f"taxa updated: {stats.taxa_updated}")
    print(f"species inserted: {stats.species_inserted}")
    print(f"species updated: {stats.species_updated}")
    print(f"flagged rows loaded: {stats.flagged}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="species_crossref.csv",
        help="Path to species_crossref.csv",
    )
    args = parser.parse_args()
    stats = load(Path(args.csv_path))
    print_stats(stats)


if __name__ == "__main__":
    main()
