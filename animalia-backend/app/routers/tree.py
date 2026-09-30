"""Reptile classification tree."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Species, Taxon
from app.schemas.taxon import TreeNode

router = APIRouter(prefix="/api/tree", tags=["tree"])

_ROOT_RANKS = {"clade", "order", "clade_group"}


def build_reptile_tree(taxa: list[Taxon], species_rows: list[Species]) -> list[TreeNode]:
    """Nest taxa by parent_id, then hang each species under its family.

    `taxa` and `species_rows` must already be loaded. This function only
    walks those lists and a dict keyed by taxon id.
    """
    taxon_by_id = {taxon.id: taxon for taxon in taxa}
    nodes: dict[int, TreeNode] = {
        taxon.id: TreeNode(id=taxon.id, name=taxon.scientific_name, rank=taxon.rank)
        for taxon in taxa
        if taxon.rank != "species"
    }

    roots: list[TreeNode] = []
    for taxon in taxa:
        node = nodes.get(taxon.id)
        if node is None:
            continue
        parent = nodes.get(taxon.parent_id) if taxon.parent_id is not None else None
        if parent is None and taxon.rank in _ROOT_RANKS:
            roots.append(node)
        elif parent is not None:
            parent.children.append(node)

    for species in species_rows:
        family_id = _family_id(species, taxon_by_id)
        family = nodes.get(family_id) if family_id is not None else None
        if family is None:
            continue
        family.children.append(
            TreeNode(id=species.id, name=species.scientific_name, rank="species")
        )

    return roots


def _family_id(species: Species, taxon_by_id: dict[int, Taxon]) -> int | None:
    """Follow parent_id links in memory until the family taxon."""
    current = taxon_by_id.get(species.taxon_id) if species.taxon_id is not None else None
    while current is not None:
        if current.rank == "family":
            return current.id
        if current.parent_id is None:
            return None
        current = taxon_by_id.get(current.parent_id)
    return None


@router.get("/reptiles", response_model=list[TreeNode])
def get_reptile_tree(db: Session = Depends(get_db)) -> list[TreeNode]:
    """Return clade → family → species for the loaded reptile tree."""
    taxa = db.query(Taxon).all()
    species_rows = db.query(Species).all()
    return build_reptile_tree(taxa, species_rows)
