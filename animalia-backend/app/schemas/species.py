"""Pydantic shapes for species endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SpeciesBase(BaseModel):
    common_name: str | None = None
    authorship: str | None = None
    iucn_status: str | None = None
    description: str | None = None
    image_url: str | None = None


class SpeciesCreate(SpeciesBase):
    taxon_id: int


class SpeciesRead(SpeciesBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    taxon_id: int
    created_at: datetime | None = None


class SpeciesWithTaxon(SpeciesRead):
    scientific_name: str | None = None
    rank: str | None = None
