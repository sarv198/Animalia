"""Pydantic shapes for taxon endpoints."""

from pydantic import BaseModel, ConfigDict


class TaxonBase(BaseModel):
    scientific_name: str
    rank: str
    parent_id: int | None = None
    col_taxon_id: str | None = None
    taxonomic_source: str | None = None


class TaxonCreate(TaxonBase):
    pass


class TaxonRead(TaxonBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TaxonNode(BaseModel):
    """Lightweight node for tree / lineage responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scientific_name: str
    rank: str
    parent_id: int | None = None
    children: list["TaxonNode"] = []
