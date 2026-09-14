"""Seed the database with a small starter taxonomy for local development."""

from __future__ import annotations

import logging

from app.database import SessionLocal, engine
from app.models import Base, Species, Taxon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEED = [
    # (scientific_name, rank, parent_name, common_name)
    ("Animalia", "kingdom", None, None),
    ("Chordata", "phylum", "Animalia", None),
    ("Mammalia", "class", "Chordata", None),
    ("Carnivora", "order", "Mammalia", None),
    ("Felidae", "family", "Carnivora", None),
    ("Panthera", "genus", "Felidae", None),
    ("Panthera leo", "species", "Panthera", "Lion"),
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        by_name: dict[str, Taxon] = {}
        for name, rank, parent_name, common in SEED:
            existing = db.query(Taxon).filter(Taxon.scientific_name == name).first()
            if existing:
                by_name[name] = existing
                continue
            parent_id = by_name[parent_name].id if parent_name else None
            taxon = Taxon(
                scientific_name=name,
                rank=rank,
                parent_id=parent_id,
            )
            db.add(taxon)
            db.flush()
            by_name[name] = taxon
            if rank == "species":
                db.add(
                    Species(
                        taxon_id=taxon.id,
                        common_name=common,
                    )
                )
        db.commit()
        logger.info("Seeded %d taxa", len(SEED))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
