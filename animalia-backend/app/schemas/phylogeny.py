"""JSON shapes for the phylogeny response."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.species import SpeciesImage


class RepresentativeSpecies(BaseModel):
    """The one species standing in for a family tip. Fetch details via /api/species/{id}.

    ``image`` is its first photo (with the credit to show beside it), so the
    tree can show the animal without a request per family.
    """

    id: int
    scientific_name: str
    common_name: str | None = None
    image: SpeciesImage | None = None


class PhyloTreeNode(BaseModel):
    """One node of the phylogeny.

    kind:
      family  a family tip, placed by its representative species
      group   a collapsed group drawn as a single tip (e.g. Pterosauria, Aves)
      clade   an internal node (common ancestor); name may be null
    """

    id: int
    name: str | None = None
    kind: Literal["family", "group", "clade"]
    source: str | None = None
    open_tree_id: str | None = None

    family: str | None = None
    clade_group: str | None = None
    representative_species: RepresentativeSpecies | None = None
    placement_status: Literal["confirmed", "flagged", "unknown"] | None = None

    extinct: bool = False
    placement_uncertain: bool = False
    anapsid_skull: bool = False
    note: str | None = None
    citation: str | None = None

    # Ages are millions of years ago. For a clade, age_ma is when its last
    # common ancestor lived; for a living tip it is 0; for an extinct group it
    # is its last fossil. stem_age_ma is the parent's age_ma: when this lineage
    # split from its closest relatives (a family's "emergence").
    age_ma: float | None = None
    age_ci_low: float | None = None
    age_ci_high: float | None = None
    age_source: Literal[
        "present", "last appearance", "fossil minimum", "TimeTree 5", "interpolated"
    ] | None = None
    age_citation: str | None = None
    age_study_count: int | None = None
    age_adjusted: bool = False
    age_unadjusted_ma: float | None = None
    stem_age_ma: float | None = None
    first_appearance_ma: float | None = None
    last_appearance_ma: float | None = None

    children: list[PhyloTreeNode] = []


PhyloTreeNode.model_rebuild()
