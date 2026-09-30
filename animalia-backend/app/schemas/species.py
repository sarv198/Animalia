"""JSON shapes for species responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

_CLADE_RANKS = {"clade", "order", "clade_group"}


class Taxonomy(BaseModel):
    """Family and the clade or order above it."""

    model_config = ConfigDict(from_attributes=True)

    family: str | None = None
    clade_group: str | None = None


class SpeciesSummary(BaseModel):
    """Short species shape for search results."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scientific_name: str
    common_name: str | None = None


class SpeciesDetail(BaseModel):
    """Species plus the family and clade/order it belongs to."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scientific_name: str
    common_name: str | None = None
    iucn_category: str | None = None
    gbif_taxon_id: int | None = None
    col_taxon_id: str | None = None
    ott_id: int | None = None
    taxonomy: Taxonomy

    @model_validator(mode="before")
    @classmethod
    def _from_species(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        family, clade_group = _taxonomy_names(getattr(data, "taxon", None))
        return {
            "id": data.id,
            "scientific_name": data.scientific_name,
            "common_name": data.common_name,
            "iucn_category": data.iucn_category,
            "gbif_taxon_id": data.gbif_taxon_id,
            "col_taxon_id": data.col_taxon_id,
            "ott_id": data.ott_id,
            "taxonomy": {"family": family, "clade_group": clade_group},
        }


def _taxonomy_names(taxon: Any) -> tuple[str | None, str | None]:
    """Walk parents of a species taxon: family, then clade or order."""
    family: str | None = None
    clade_group: str | None = None
    current = taxon
    if current is not None and (getattr(current, "rank", "") or "").lower() == "species":
        current = getattr(current, "parent", None)
    while current is not None:
        rank = (getattr(current, "rank", "") or "").lower()
        if rank == "family" and family is None:
            family = current.scientific_name
        elif rank in _CLADE_RANKS and clade_group is None:
            clade_group = current.scientific_name
        current = getattr(current, "parent", None)
    return family, clade_group
