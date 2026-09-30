"""Search endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.crud import taxa as taxa_crud
from app.database import get_db
from app.schemas.taxon import TreeNode

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/taxa", response_model=list[TreeNode])
def search_taxa(
    q: str = Query(..., min_length=1, description="Scientific name substring"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[TreeNode]:
    return [
        TreeNode(id=row.id, name=row.scientific_name, rank=row.rank)
        for row in taxa_crud.search_by_name(db, q, limit=limit)
    ]
