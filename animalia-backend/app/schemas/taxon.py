"""Pydantic shapes for taxon endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TaxonBase(BaseModel):
    scientific_name: str
    rank: str
    parent_id: int | None = None
    col_id: str | None = None
    ott_id: str | None = None
    gbif_id: str | None = None


class TaxonCreate(TaxonBase):
    pass


class TaxonRead(TaxonBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None


class TaxonNode(BaseModel):
    """Lightweight node for tree / lineage responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scientific_name: str
    rank: str
    parent_id: int | None = None
    children: list["TaxonNode"] = []
