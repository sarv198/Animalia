"""Taxon endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import taxa as taxa_crud
from app.database import get_db
from app.schemas.taxon import TaxonRead

router = APIRouter(prefix="/taxa", tags=["taxa"])


@router.get("/", response_model=list[TaxonRead])
def list_taxa(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    rank: str | None = None,
    db: Session = Depends(get_db),
) -> list[TaxonRead]:
    return taxa_crud.list_taxa(db, skip=skip, limit=limit, rank=rank)


@router.get("/{taxon_id}", response_model=TaxonRead)
def get_taxon(taxon_id: int, db: Session = Depends(get_db)) -> TaxonRead:
    row = taxa_crud.get_taxon(db, taxon_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Taxon not found")
    return row


@router.get("/{taxon_id}/children", response_model=list[TaxonRead])
def get_children(taxon_id: int, db: Session = Depends(get_db)) -> list[TaxonRead]:
    if taxa_crud.get_taxon(db, taxon_id) is None:
        raise HTTPException(status_code=404, detail="Taxon not found")
    return taxa_crud.get_children(db, taxon_id)
