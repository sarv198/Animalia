"""DB query helpers for species."""

from sqlalchemy.orm import Session, joinedload

from app.models import Species


def get_species(db: Session, species_id: int) -> Species | None:
    return (
        db.query(Species)
        .options(joinedload(Species.taxon))
        .filter(Species.id == species_id)
        .first()
    )


def list_species(
    db: Session, *, skip: int = 0, limit: int = 50
) -> list[Species]:
    return (
        db.query(Species)
        .options(joinedload(Species.taxon))
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_by_taxon_id(db: Session, taxon_id: int) -> Species | None:
    return db.query(Species).filter(Species.taxon_id == taxon_id).first()
