"""Taxon endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import taxa as taxa_crud
from app.database import get_db
from app.schemas.taxon import TreeNode

router = APIRouter(prefix="/taxa", tags=["taxa"])


def _flat_node(taxon) -> TreeNode:
    return TreeNode(id=taxon.id, name=taxon.scientific_name, rank=taxon.rank)


@router.get("/", response_model=list[TreeNode])
def list_taxa(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    rank: str | None = None,
    db: Session = Depends(get_db),
) -> list[TreeNode]:
    return [
        _flat_node(row)
        for row in taxa_crud.list_taxa(db, skip=skip, limit=limit, rank=rank)
    ]


@router.get("/{taxon_id}", response_model=TreeNode)
def get_taxon(taxon_id: int, db: Session = Depends(get_db)) -> TreeNode:
    row = taxa_crud.get_taxon(db, taxon_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Taxon not found")
    return _flat_node(row)


@router.get("/{taxon_id}/children", response_model=list[TreeNode])
def get_children(taxon_id: int, db: Session = Depends(get_db)) -> list[TreeNode]:
    if taxa_crud.get_taxon(db, taxon_id) is None:
        raise HTTPException(status_code=404, detail="Taxon not found")
    return [_flat_node(row) for row in taxa_crud.get_children(db, taxon_id)]
