"""Species detail and search."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.models import Species, Taxon
from app.schemas.species import SpeciesDetail, SpeciesSummary

router = APIRouter(prefix="/api", tags=["species"])


@router.get("/species/{species_id}", response_model=SpeciesDetail)
def get_species(species_id: int, db: Session = Depends(get_db)) -> SpeciesDetail:
    """Return one species and the family and clade or order above it."""
    row = (
        db.query(Species)
        .options(
            joinedload(Species.taxon)
            .joinedload(Taxon.parent)
            .joinedload(Taxon.parent),
            selectinload(Species.media),
        )
        .filter(Species.id == species_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Species not found")
    return SpeciesDetail.model_validate(row)


@router.get("/search", response_model=list[SpeciesSummary])
def search_species(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> list[SpeciesSummary]:
    """Case-insensitive partial match on scientific name or common name."""
    pattern = f"%{q.strip()}%"
    return (
        db.query(Species)
        .filter(
            or_(
                Species.scientific_name.ilike(pattern),
                Species.common_name.ilike(pattern),
            )
        )
        .limit(20)
        .all()
    )
