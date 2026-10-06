"""Data-quality assertions against taxa, species and the phylogeny already loaded in Postgres."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PhyloNode, PhylogenyEdge, Species, SpeciesMedia, Taxon
from etl.extract.media import ALLOWED_LICENCES, licence_family, usable

VALID_IUCN_CODES = frozenset({"LC", "NT", "VU", "EN", "CR", "EW", "EX", "DD"})
VALID_PLACEMENT_STATUSES = frozenset({"confirmed", "flagged", "unknown"})


class ValidationError(Exception):
    """A data-quality check failed. The message names the offending rows."""


def _species_label(species: Species) -> str:
    return f"species id={species.id} scientific_name={species.scientific_name!r}"


def _taxon_label(taxon: Taxon) -> str:
    return (
        f"taxon id={taxon.id} scientific_name={taxon.scientific_name!r} "
        f"rank={taxon.rank!r} parent_id={taxon.parent_id}"
    )


def check_species_have_taxon(db: Session) -> None:
    """Every species row must point at a taxon."""
    rows = (
        db.query(Species)
        .filter(Species.taxon_id.is_(None))
        .order_by(Species.id)
        .all()
    )
    if rows:
        listed = "; ".join(_species_label(row) for row in rows)
        raise ValidationError(f"species with null taxon_id: {listed}")


def check_no_self_parent(db: Session) -> None:
    """No taxon may be its own parent."""
    rows = (
        db.query(Taxon)
        .filter(Taxon.parent_id.isnot(None), Taxon.parent_id == Taxon.id)
        .order_by(Taxon.id)
        .all()
    )
    if rows:
        listed = "; ".join(_taxon_label(row) for row in rows)
        raise ValidationError(f"taxon is its own parent: {listed}")


def check_no_orphan_taxa(db: Session) -> None:
    """parent_id must reference an existing taxon when it is set."""
    taxon_ids = {row.id for row in db.query(Taxon.id).all()}
    rows = (
        db.query(Taxon)
        .filter(Taxon.parent_id.isnot(None))
        .order_by(Taxon.id)
        .all()
    )
    orphans = [row for row in rows if row.parent_id not in taxon_ids]
    if orphans:
        listed = "; ".join(_taxon_label(row) for row in orphans)
        raise ValidationError(f"orphan taxa (parent_id missing): {listed}")


def check_unique_species_names(db: Session) -> None:
    """species.scientific_name values must be unique."""
    duplicates = (
        db.query(Species.scientific_name, func.count(Species.id))
        .group_by(Species.scientific_name)
        .having(func.count(Species.id) > 1)
        .all()
    )
    if not duplicates:
        return

    parts: list[str] = []
    for name, _count in duplicates:
        ids = [
            row.id
            for row in db.query(Species.id)
            .filter(Species.scientific_name == name)
            .order_by(Species.id)
            .all()
        ]
        parts.append(f"scientific_name={name!r} ids={ids}")
    raise ValidationError("duplicate species scientific_name: " + "; ".join(parts))


def check_iucn_codes(db: Session) -> None:
    """A non-null iucn_category must be a valid IUCN code."""
    rows = (
        db.query(Species)
        .filter(Species.iucn_category.isnot(None))
        .order_by(Species.id)
        .all()
    )
    invalid = [
        row
        for row in rows
        if (row.iucn_category or "").strip() not in VALID_IUCN_CODES
    ]
    if invalid:
        listed = "; ".join(
            f"{_species_label(row)} iucn_category={row.iucn_category!r}"
            for row in invalid
        )
        raise ValidationError(f"invalid iucn_category: {listed}")


def _node_label(node: PhyloNode) -> str:
    return f"phylo node id={node.id} label={node.label!r} external_id={node.external_id!r}"


def check_phylogeny_is_one_tree(db: Session) -> None:
    """phylo_nodes form one rooted tree: a single root, every node reachable, no cycles."""
    nodes = {node.id: node for node in db.query(PhyloNode).all()}
    if not nodes:
        raise ValidationError("phylo_nodes is empty; the phylogeny was not loaded")
    children: dict[int, list[int]] = {}
    has_parent: set[int] = set()
    for edge in db.query(PhylogenyEdge).all():
        children.setdefault(edge.parent_node_id, []).append(edge.child_node_id)
        has_parent.add(edge.child_node_id)
    roots = [node_id for node_id in nodes if node_id not in has_parent]
    if len(roots) != 1:
        listed = "; ".join(_node_label(nodes[r]) for r in roots)
        raise ValidationError(f"phylogeny needs exactly one root, found {len(roots)}: {listed}")
    seen: set[int] = set()
    stack = [roots[0]]
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            raise ValidationError(f"phylogeny cycle at {_node_label(nodes[node_id])}")
        seen.add(node_id)
        stack.extend(children.get(node_id, []))
    unreachable = sorted(set(nodes) - seen)
    if unreachable:
        listed = "; ".join(_node_label(nodes[n]) for n in unreachable)
        raise ValidationError(f"phylo nodes not reachable from the root: {listed}")
    unary = [nodes[n] for n, kids in children.items() if len(kids) == 1]
    if unary:
        listed = "; ".join(_node_label(n) for n in unary)
        raise ValidationError(f"phylo nodes with a single child: {listed}")


def check_every_species_is_one_tip(db: Session) -> None:
    """Each species with an OTT id is the representative of exactly one family tip."""
    counts = dict(
        db.query(PhyloNode.species_id, func.count(PhyloNode.id))
        .filter(PhyloNode.species_id.isnot(None))
        .group_by(PhyloNode.species_id)
        .all()
    )
    rows = db.query(Species).filter(Species.ott_id.isnot(None)).order_by(Species.id).all()
    wrong = [row for row in rows if counts.get(row.id, 0) != 1]
    if wrong:
        listed = "; ".join(
            f"{_species_label(row)} tips={counts.get(row.id, 0)}" for row in wrong
        )
        raise ValidationError(f"species not represented by exactly one tip: {listed}")


def check_phylogeny_tips(db: Session) -> None:
    """Tips are either a family (species + family + status) or a collapsed group."""
    problems: list[str] = []
    for node in db.query(PhyloNode).order_by(PhyloNode.id).all():
        is_family = node.species_id is not None
        if is_family and (node.family_taxon_id is None or not node.is_tip):
            problems.append(f"{_node_label(node)} family tip missing family or not a tip")
        if is_family and node.placement_status not in VALID_PLACEMENT_STATUSES:
            problems.append(f"{_node_label(node)} placement_status={node.placement_status!r}")
        if node.is_tip and not is_family and not node.collapsed_group:
            problems.append(f"{_node_label(node)} tip is neither a family nor a group")
        if not node.is_tip and (is_family or node.collapsed_group):
            problems.append(f"{_node_label(node)} internal node marked as family or group")
    if problems:
        raise ValidationError("bad phylogeny tips: " + "; ".join(problems))


MAX_AGE_MA = 400.0
VALID_AGE_SOURCES = frozenset(
    {"present", "last appearance", "fossil minimum", "TimeTree 5", "interpolated"}
)


def check_phylogeny_ages(db: Session) -> None:
    """Every node is dated, sourced and in range, and no ancestor is younger
    than a descendant or than an extinct descendant's first fossil."""
    nodes = {node.id: node for node in db.query(PhyloNode).all()}
    problems: list[str] = []
    for node in nodes.values():
        label = _node_label(node)
        if node.age_ma is None or node.age_source not in VALID_AGE_SOURCES:
            problems.append(f"{label} age={node.age_ma} source={node.age_source!r}")
            continue
        if not 0 <= node.age_ma <= MAX_AGE_MA:
            problems.append(f"{label} age {node.age_ma} out of range")
        if node.is_tip and not node.extinct and node.age_ma != 0:
            problems.append(f"{label} living tip not at 0 Ma")
        if node.extinct and node.is_tip and (
            node.first_appearance_ma is None
            or node.last_appearance_ma is None
            or node.first_appearance_ma < node.last_appearance_ma
        ):
            problems.append(f"{label} extinct tip needs first >= last appearance")
        if node.age_ci_low is not None and node.age_ci_high is not None and node.age_ci_low > node.age_ci_high:
            problems.append(f"{label} confidence interval reversed")
        if node.age_source not in {"present", "interpolated"} and not node.age_citation:
            problems.append(f"{label} age has no citation")
        if node.age_adjusted and node.age_unadjusted_ma is None:
            problems.append(f"{label} adjusted without the original estimate")
    for edge in db.query(PhylogenyEdge).all():
        parent, child = nodes[edge.parent_node_id], nodes[edge.child_node_id]
        if parent.age_ma is None or child.age_ma is None:
            continue
        oldest_child = max(child.age_ma, child.first_appearance_ma or 0)
        if oldest_child > parent.age_ma + 1e-6:
            problems.append(
                f"{_node_label(child)} ({oldest_child} Ma) is older than its parent "
                f"{_node_label(parent)} ({parent.age_ma} Ma)"
            )
    if problems:
        raise ValidationError("bad phylogeny ages: " + "; ".join(problems))


def check_media(db: Session) -> None:
    """Every image is openly licensed, served over https and creditable; every
    IUCN status says where it came from."""
    problems: list[str] = []
    for media in db.query(SpeciesMedia).order_by(SpeciesMedia.id).all():
        label = f"media id={media.id} species_id={media.species_id}"
        if licence_family(media.licence) not in ALLOWED_LICENCES:
            problems.append(f"{label} licence {media.licence!r} not allowed")
        elif not usable(media.licence, media.creator):
            problems.append(f"{label} has no creator to credit")
        if not media.image_url.startswith("https://"):
            problems.append(f"{label} image not served over https")
        if not (media.creator or media.page_url):
            problems.append(f"{label} has no creator or source page to credit")
    for species in db.query(Species).filter(Species.iucn_category.isnot(None)).all():
        if not species.iucn_source:
            problems.append(f"{_species_label(species)} IUCN status without a source")
    if problems:
        raise ValidationError("bad species media: " + "; ".join(problems))


def run(db: Session | None = None) -> None:
    """Run every check. Raises ValidationError on the first failure."""
    own_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        check_species_have_taxon(db)
        check_no_self_parent(db)
        check_no_orphan_taxa(db)
        check_unique_species_names(db)
        check_iucn_codes(db)
        check_phylogeny_is_one_tree(db)
        check_every_species_is_one_tip(db)
        check_phylogeny_tips(db)
        check_phylogeny_ages(db)
        check_media(db)
    finally:
        if own_session:
            db.close()


def main() -> None:
    run()
    print("all checks passed")


if __name__ == "__main__":
    main()
