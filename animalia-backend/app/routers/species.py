"""Species endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import species as species_crud
from app.database import get_db
from app.schemas.species import SpeciesRead, SpeciesWithTaxon

router = APIRouter(prefix="/species", tags=["species"])


@router.get("/", response_model=list[SpeciesRead])
def list_species(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[SpeciesRead]:
    return species_crud.list_species(db, skip=skip, limit=limit)


@router.get("/{species_id}", response_model=SpeciesWithTaxon)
def get_species(species_id: int, db: Session = Depends(get_db)) -> SpeciesWithTaxon:
    row = species_crud.get_species(db, species_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Species not found")
    return SpeciesWithTaxon(
        id=row.id,
        taxon_id=row.taxon_id,
        scientific_name=row.scientific_name,
        common_name=row.common_name,
        accepted_name=row.accepted_name,
        col_taxon_id=row.col_taxon_id,
        gbif_taxon_id=row.gbif_taxon_id,
        ott_id=row.ott_id,
        iucn_category=row.iucn_category,
        iucn_assessment_year=row.iucn_assessment_year,
        occurrence_count=row.occurrence_count,
        rank=row.taxon.rank if row.taxon else None,
    )
