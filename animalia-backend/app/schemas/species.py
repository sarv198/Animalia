"""Pydantic shapes for species endpoints."""

from pydantic import BaseModel, ConfigDict


class SpeciesBase(BaseModel):
    scientific_name: str
    common_name: str | None = None
    accepted_name: str | None = None
    col_taxon_id: str | None = None
    gbif_taxon_id: int | None = None
    ott_id: int | None = None
    iucn_category: str | None = None
    iucn_assessment_year: int | None = None
    occurrence_count: int | None = None


class SpeciesCreate(SpeciesBase):
    taxon_id: int | None = None


class SpeciesRead(SpeciesBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    taxon_id: int | None = None


class SpeciesWithTaxon(SpeciesRead):
    rank: str | None = None
