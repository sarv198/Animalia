"""DB query helpers for taxa."""

from sqlalchemy.orm import Session

from app.models import Taxon


def get_taxon(db: Session, taxon_id: int) -> Taxon | None:
    return db.query(Taxon).filter(Taxon.id == taxon_id).first()


def list_taxa(
    db: Session, *, skip: int = 0, limit: int = 50, rank: str | None = None
) -> list[Taxon]:
    q = db.query(Taxon)
    if rank:
        q = q.filter(Taxon.rank == rank)
    return q.offset(skip).limit(limit).all()


def get_children(db: Session, parent_id: int) -> list[Taxon]:
    return db.query(Taxon).filter(Taxon.parent_id == parent_id).all()


def search_by_name(db: Session, query: str, *, limit: int = 25) -> list[Taxon]:
    pattern = f"%{query}%"
    return (
        db.query(Taxon)
        .filter(Taxon.scientific_name.ilike(pattern))
        .limit(limit)
        .all()
    )
