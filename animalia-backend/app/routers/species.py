"""Species endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import species as species_crud
from app.database import get_db
from app.schemas.species import SpeciesDetail, SpeciesSummary

router = APIRouter(prefix="/species", tags=["species"])


@router.get("/", response_model=list[SpeciesSummary])
def list_species(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[SpeciesSummary]:
    return species_crud.list_species(db, skip=skip, limit=limit)


@router.get("/{species_id}", response_model=SpeciesDetail)
def get_species(species_id: int, db: Session = Depends(get_db)) -> SpeciesDetail:
    row = species_crud.get_species(db, species_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Species not found")
    return SpeciesDetail.model_validate(row)
