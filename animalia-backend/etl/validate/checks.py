"""Data-quality assertions against taxa and species already loaded in Postgres."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Species, Taxon

VALID_IUCN_CODES = frozenset({"LC", "NT", "VU", "EN", "CR", "EW", "EX", "DD"})


class ValidationError(Exception):
    """A data-quality check failed. The message names the offending rows."""


def _species_label(species: Species) -> str:
    return f"species id={species.id} scientific_name={species.scientific_name!r}"


def _taxon_label(taxon: Taxon) -> str:
    return (
        f"taxon id={taxon.id} scientific_name={taxon.scientific_name!r} "
        f"rank={taxon.rank!r} parent_id={taxon.parent_id}"
    )


def check_species_have_taxon(db: Session) -> None:
    """Every species row must point at a taxon."""
    rows = (
        db.query(Species)
        .filter(Species.taxon_id.is_(None))
        .order_by(Species.id)
        .all()
    )
    if rows:
        listed = "; ".join(_species_label(row) for row in rows)
        raise ValidationError(f"species with null taxon_id: {listed}")


def check_no_self_parent(db: Session) -> None:
    """No taxon may be its own parent."""
    rows = (
        db.query(Taxon)
        .filter(Taxon.parent_id.isnot(None), Taxon.parent_id == Taxon.id)
        .order_by(Taxon.id)
        .all()
    )
    if rows:
        listed = "; ".join(_taxon_label(row) for row in rows)
        raise ValidationError(f"taxon is its own parent: {listed}")


def check_no_orphan_taxa(db: Session) -> None:
    """parent_id must reference an existing taxon when it is set."""
    taxon_ids = {row.id for row in db.query(Taxon.id).all()}
    rows = (
        db.query(Taxon)
        .filter(Taxon.parent_id.isnot(None))
        .order_by(Taxon.id)
        .all()
    )
    orphans = [row for row in rows if row.parent_id not in taxon_ids]
    if orphans:
        listed = "; ".join(_taxon_label(row) for row in orphans)
        raise ValidationError(f"orphan taxa (parent_id missing): {listed}")


def check_unique_species_names(db: Session) -> None:
    """species.scientific_name values must be unique."""
    duplicates = (
        db.query(Species.scientific_name, func.count(Species.id))
        .group_by(Species.scientific_name)
        .having(func.count(Species.id) > 1)
        .all()
    )
    if not duplicates:
        return

    parts: list[str] = []
    for name, _count in duplicates:
        ids = [
            row.id
            for row in db.query(Species.id)
            .filter(Species.scientific_name == name)
            .order_by(Species.id)
            .all()
        ]
        parts.append(f"scientific_name={name!r} ids={ids}")
    raise ValidationError("duplicate species scientific_name: " + "; ".join(parts))


def check_iucn_codes(db: Session) -> None:
    """A non-null iucn_category must be a valid IUCN code."""
    rows = (
        db.query(Species)
        .filter(Species.iucn_category.isnot(None))
        .order_by(Species.id)
        .all()
    )
    invalid = [
        row
        for row in rows
        if (row.iucn_category or "").strip() not in VALID_IUCN_CODES
    ]
    if invalid:
        listed = "; ".join(
            f"{_species_label(row)} iucn_category={row.iucn_category!r}"
            for row in invalid
        )
        raise ValidationError(f"invalid iucn_category: {listed}")


def run(db: Session | None = None) -> None:
    """Run every check. Raises ValidationError on the first failure."""
    own_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        check_species_have_taxon(db)
        check_no_self_parent(db)
        check_no_orphan_taxa(db)
        check_unique_species_names(db)
        check_iucn_codes(db)
    finally:
        if own_session:
            db.close()


def main() -> None:
    run()
    print("all checks passed")


if __name__ == "__main__":
    main()
