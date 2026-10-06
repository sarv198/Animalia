"""Reptile phylogeny: evolutionary relationships between families."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import PhyloNode, PhylogenyEdge, Source, Species, Taxon
from app.schemas.phylogeny import PhyloTreeNode, RepresentativeSpecies
from app.schemas.species import SpeciesImage

router = APIRouter(prefix="/api/phylogeny", tags=["phylogeny"])


def _kind(node: PhyloNode) -> str:
    if node.species_id is not None:
        return "family"
    if node.collapsed_group:
        return "group"
    return "clade"


def _to_schema(node: PhyloNode) -> PhyloTreeNode:
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
    nodes: list[PhyloNode], edges: list[PhylogenyEdge]
) -> PhyloTreeNode | None:
    """Nest already-loaded nodes by their edges and return the root.

    Children keep load order (edge id), which preserves Open Tree's ordering.
    """
    built = {node.id: _to_schema(node) for node in nodes}
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
    root = build_phylogeny_tree(nodes, db.query(PhylogenyEdge).all())
    if root is None:
        raise HTTPException(status_code=500, detail="Phylogeny does not have a single root")
    return root
