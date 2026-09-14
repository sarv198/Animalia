"""Tree / phylogeny endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import taxa as taxa_crud
from app.database import get_db
from app.schemas.taxon import TaxonNode

router = APIRouter(prefix="/tree", tags=["tree"])


@router.get("/subtree/{taxon_id}", response_model=TaxonNode)
def get_subtree(
    taxon_id: int,
    depth: int = Query(1, ge=1, le=5),
    db: Session = Depends(get_db),
) -> TaxonNode:
    """Return a taxon and nested children up to `depth` levels."""
    root = taxa_crud.get_taxon(db, taxon_id)
    if root is None:
        raise HTTPException(status_code=404, detail="Taxon not found")
    return _build_node(db, root, depth)


def _build_node(db: Session, taxon, depth: int) -> TaxonNode:
    children: list[TaxonNode] = []
    if depth > 0:
        for child in taxa_crud.get_children(db, taxon.id):
            children.append(_build_node(db, child, depth - 1))
    return TaxonNode(
        id=taxon.id,
        scientific_name=taxon.scientific_name,
        rank=taxon.rank,
        parent_id=taxon.parent_id,
        children=children,
    )
