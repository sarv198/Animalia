"""Reptile phylogeny: evolutionary relationships between families."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import FamilyProfile, PhyloNode, PhylogenyEdge, Source, Species, Taxon, TaxonSummary
from app.schemas.phylogeny import (
    NodeProfile,
    OccurrenceMap,
    PhyloTreeNode,
    RangeMap,
    RepresentativeSpecies,
    TaxonText,
)
from app.schemas.species import SpeciesImage

router = APIRouter(prefix="/api/phylogeny", tags=["phylogeny"])


def _kind(node: PhyloNode) -> str:
    if node.species_id is not None:
        return "family"
    if node.collapsed_group:
        return "group"
    return "clade"


def _to_schema(node: PhyloNode, species_counts: dict[str, int] | None = None) -> PhyloTreeNode:
    family = node.family_taxon
    clade_group = family.parent.scientific_name if family and family.parent else None
    species = node.species
    return PhyloTreeNode(
        id=node.id,
        name=node.label,
        kind=_kind(node),
        source=node.source.source_name if node.source else None,
        open_tree_id=node.external_id,
        family=family.scientific_name if family else None,
        clade_group=clade_group,
        representative_species=(
            RepresentativeSpecies(
                id=species.id,
                scientific_name=species.scientific_name,
                common_name=species.common_name,
                image=_first_image(species),
            )
            if species
            else None
        ),
        placement_status=node.placement_status,
        species_count=(species_counts or {}).get(node.label) if species else None,
        extinct=node.extinct,
        placement_uncertain=node.placement_uncertain,
        anapsid_skull=node.anapsid_skull,
        note=node.note,
        citation=node.citation,
        age_ma=node.age_ma,
        age_ci_low=node.age_ci_low,
        age_ci_high=node.age_ci_high,
        age_source=node.age_source,
        age_citation=node.age_citation,
        age_study_count=node.age_study_count,
        age_adjusted=node.age_adjusted,
        age_unadjusted_ma=node.age_unadjusted_ma,
        first_appearance_ma=node.first_appearance_ma,
        last_appearance_ma=node.last_appearance_ma,
    )


def _first_image(species: Species) -> SpeciesImage | None:
    media = list(getattr(species, "media", None) or [])
    if not media:
        return None
    m = media[0]
    return SpeciesImage(
        url=m.image_url,
        thumbnail_url=m.thumbnail_url,
        source=m.source,
        page_url=m.page_url,
        licence=m.licence,
        licence_url=m.licence_url,
        creator=m.creator,
    )


def build_phylogeny_tree(
    nodes: list[PhyloNode],
    edges: list[PhylogenyEdge],
    species_counts: dict[str, int] | None = None,
) -> PhyloTreeNode | None:
    """Nest already-loaded nodes by their edges and return the root.

    Children keep load order (edge id), which preserves Open Tree's ordering.
    """
    built = {node.id: _to_schema(node, species_counts) for node in nodes}
    has_parent: set[int] = set()
    for edge in sorted(edges, key=lambda e: e.id):
        parent, child = built[edge.parent_node_id], built[edge.child_node_id]
        parent.children.append(child)
        child.stem_age_ma = parent.age_ma
        has_parent.add(edge.child_node_id)
    roots = [built[node_id] for node_id in built if node_id not in has_parent]
    return roots[0] if len(roots) == 1 else None


class DataSource(BaseModel):
    name: str
    version: str | None = None
    url: str | None = None


@router.get("/sources", response_model=list[DataSource])
def get_sources(db: Session = Depends(get_db)) -> list[DataSource]:
    """The datasets behind the tree, with the versions loaded (for credits)."""
    return [
        DataSource(name=s.source_name, version=s.source_version, url=s.source_url)
        for s in db.query(Source).order_by(Source.id).all()
    ]


@router.get("/reptiles", response_model=PhyloTreeNode)
def get_reptile_phylogeny(db: Session = Depends(get_db)) -> PhyloTreeNode:
    """Return the reptile phylogeny as one nested tree, rooted at Reptilia."""
    nodes = (
        db.query(PhyloNode)
        .options(
            joinedload(PhyloNode.species).selectinload(Species.media),
            joinedload(PhyloNode.source),
            joinedload(PhyloNode.family_taxon).joinedload(Taxon.parent),
        )
        .all()
    )
    if not nodes:
        raise HTTPException(
            status_code=404,
            detail="Phylogeny not loaded. Run: python etl/run_pipeline.py",
        )
    species_counts = {
        p.family: p.species_count for p in db.query(FamilyProfile).all() if p.species_count is not None
    }
    root = build_phylogeny_tree(nodes, db.query(PhylogenyEdge).all(), species_counts)
    if root is None:
        raise HTTPException(status_code=500, detail="Phylogeny does not have a single root")
    return root


@router.get("/profile/{name}", response_model=NodeProfile)
def get_profile(name: str, db: Session = Depends(get_db)) -> NodeProfile:
    """Description, species count and range map for a named family, clade or
    group. Ranges are GARD 1.7 polygons; when a family has none, `occurrences`
    names the representative species so GBIF records can be mapped instead."""
    node = (
        db.query(PhyloNode)
        .options(joinedload(PhyloNode.species))
        .filter(PhyloNode.label == name)
        .first()
    )
    if node is None:
        raise HTTPException(status_code=404, detail=f"No node named {name!r} in the tree")
    summary = db.query(TaxonSummary).filter(TaxonSummary.name == name).first()
    profile = db.query(FamilyProfile).filter(FamilyProfile.family == name).first()
    out = NodeProfile(
        name=name,
        summary=(
            TaxonText(
                text=summary.extract, title=summary.title, url=summary.url,
                licence=summary.licence, licence_url=summary.licence_url,
                range_text=summary.range_text, range_scope=summary.range_scope,
                range_title=summary.range_title, range_url=summary.range_url,
            )
            if summary
            else None
        ),
    )
    if profile:
        out.species_count = profile.species_count
        out.checklist_release = profile.checklist_release
        if profile.range_geojson:
            out.family_range = RangeMap(
                level="family", geojson=profile.range_geojson,
                species_mapped=profile.range_species_mapped, species_total=profile.species_count,
                source=profile.range_source, citation=profile.range_citation,
            )
        if profile.rep_range_geojson:
            out.species_range = RangeMap(
                level="species", geojson=profile.rep_range_geojson,
                scientific_name=profile.rep_scientific_name,
                source=profile.range_source, citation=profile.range_citation,
            )
    species = node.species
    if species and species.gbif_taxon_id:
        out.occurrences = OccurrenceMap(
            gbif_taxon_key=species.gbif_taxon_id, scientific_name=species.scientific_name
        )
    return out
