"""Turn cached Open Tree output plus the curated backbone into loadable nodes.

Two sources, one tree:

  - Open Tree of Life supplies the branching order *inside* each living group
    (Lepidosauria, Testudines, Crocodylia), via the induced subtree of the
    representative species. Each species tip stands for its family.
  - data/curated/reptile_backbone.csv supplies everything above those groups,
    including extinct groups Open Tree cannot place (pterosaurs, dinosaurs,
    mesosaurs). A living backbone group is "anchored" to Open Tree as the most
    recent common ancestor of two named families (a node-based clade definition).

The backbone must not contradict Open Tree. For every backbone clade that
contains two or more anchors, Open Tree's common ancestor of those anchors must
contain no tips from any other anchor; otherwise building fails.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from etl.config import BACKBONE_PATH, CLADE_NAMES_PATH, OPENTREE_RAW_DIR
from etl.extract.opentree import ABOUT_FILE, SUBTREE_FILE, read_crossref
from etl.transform import newick

logger = logging.getLogger(__name__)

SOURCE_OPENTREE = "opentree"
SOURCE_BACKBONE = "curated_backbone"

# Family placement, from the whole-family check (etl/transform/family_check.py).
STATUS_CONFIRMED = "confirmed"  # all the family's species form one branch in Open Tree
STATUS_FLAGGED = "flagged"      # they do not; see the note for how they split
STATUS_UNKNOWN = "unknown"      # none of its species are in Open Tree's tree

_LABEL_RE = re.compile(r"^(?:(?P<name>.*?)\s+)?(?P<node_id>mrcaott\d+ott\d+|ott\d+)$")
# Open Tree disambiguates homonyms, e.g. "Squamata (order in Deuterostomia)".
_HOMONYM_TAG_RE = re.compile(r"\s+\((?:[a-z]+ )?in [A-Z][A-Za-z]+\)$")


class PhylogenyBuildError(ValueError):
    """The inputs cannot be assembled into a consistent tree."""


@dataclass
class Clade:
    """A node of the Open Tree subtree after single-child chains are removed."""

    node_id: str
    name: str | None
    children: list[Clade] = field(default_factory=list)

    @property
    def is_tip(self) -> bool:
        return not self.children

    def tips(self) -> list[Clade]:
        out: list[Clade] = []
        stack = [self]
        while stack:
            node = stack.pop()
            if node.is_tip:
                out.append(node)
            else:
                stack.extend(reversed(node.children))
        return out


@dataclass
class BackboneRow:
    name: str
    parent: str | None
    anchor_families: list[str]
    extinct: bool
    collapsed_group: bool
    placement_uncertain: bool
    anapsid_skull: bool
    note: str | None
    citation: str | None


@dataclass
class PhyloRecord:
    """One node ready to load. Records are emitted parents-first."""

    key: str
    parent_key: str | None
    label: str | None
    source: str
    external_id: str | None = None
    species_ott_id: int | None = None
    family: str | None = None
    family_ott_id: int | None = None
    placement_status: str | None = None
    extinct: bool = False
    collapsed_group: bool = False
    placement_uncertain: bool = False
    anapsid_skull: bool = False
    note: str | None = None
    citation: str | None = None
    # Filled by etl/transform/date_phylogeny.py
    age_ma: float | None = None
    age_ci_low: float | None = None
    age_ci_high: float | None = None
    age_source: str | None = None
    age_citation: str | None = None
    age_adjusted: bool = False
    age_unadjusted_ma: float | None = None
    age_study_count: int | None = None
    first_appearance_ma: float | None = None
    last_appearance_ma: float | None = None


@dataclass
class PhylogenyBuild:
    records: list[PhyloRecord]
    synth_id: str


# --------------------------------------------------------------------------- #
# Open Tree subtree
# --------------------------------------------------------------------------- #


def parse_label(label: str | None) -> tuple[str | None, str | None]:
    """Split an Open Tree 'name_and_id' label into (name, node_id).

    'Alligator mississippiensis ott335590' -> ('Alligator mississippiensis', 'ott335590')
    'mrcaott246ott31216'                    -> (None, 'mrcaott246ott31216')
    """
    if not label:
        return None, None
    match = _LABEL_RE.match(label.strip())
    if match is None:
        return label.strip(), None
    name = match.group("name")
    if name:
        name = _HOMONYM_TAG_RE.sub("", name) or None
    return name, match.group("node_id")


def collapse(node: newick.NewickNode) -> Clade:
    """Drop single-child chains, keeping the branching nodes and the tips.

    A branching node without its own name borrows the nearest name from the
    chain directly above it: that ancestor contains exactly the same sampled
    tips, so the name is accurate for this tree.
    """
    chain_names: list[str] = []
    while len(node.children) == 1:
        name, _ = parse_label(node.label)
        if name:
            chain_names.append(name)
        node = node.children[0]
    name, node_id = parse_label(node.label)
    if node_id is None:
        raise PhylogenyBuildError(f"node without an Open Tree id: {node.label!r}")
    if not node.children:
        return Clade(node_id=node_id, name=name)
    label = name or (chain_names[-1] if chain_names else None)
    return Clade(node_id=node_id, name=label, children=[collapse(c) for c in node.children])


@dataclass
class FamilyPlacement:
    """Whether a family forms one branch, and the note shown with its tip."""

    ott_id: int | None
    status: str
    note: str | None = None


_UNPLACED = FamilyPlacement(ott_id=None, status=STATUS_UNKNOWN)


def _parent_map(root: Clade) -> dict[int, Clade | None]:
    parents: dict[int, Clade | None] = {id(root): None}
    stack = [root]
    while stack:
        node = stack.pop()
        for child in node.children:
            parents[id(child)] = node
            stack.append(child)
    return parents


def mrca(nodes: list[Clade], parents: dict[int, Clade | None]) -> Clade:
    """Most recent common ancestor of ``nodes`` within one tree."""
    def ancestry(node: Clade) -> list[Clade]:
        path = []
        current: Clade | None = node
        while current is not None:
            path.append(current)
            current = parents[id(current)]
        return path

    common = {id(n) for n in ancestry(nodes[0])}
    for node in nodes[1:]:
        common &= {id(n) for n in ancestry(node)}
    for candidate in ancestry(nodes[0]):
        if id(candidate) in common:
            return candidate
    raise PhylogenyBuildError("nodes do not share a root")


# --------------------------------------------------------------------------- #
# Curated backbone
# --------------------------------------------------------------------------- #


def _flag(value: str | None) -> bool:
    text = (value or "").strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0", ""}:
        return False
    raise PhylogenyBuildError(f"not a boolean: {value!r}")


def load_backbone(path: Path) -> list[BackboneRow]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = [
            BackboneRow(
                name=row["name"].strip(),
                parent=(row["parent"] or "").strip() or None,
                anchor_families=[
                    f.strip() for f in (row["anchor_families"] or "").split(";") if f.strip()
                ],
                extinct=_flag(row["extinct"]),
                collapsed_group=_flag(row["collapsed_group"]),
                placement_uncertain=_flag(row["placement_uncertain"]),
                anapsid_skull=_flag(row["anapsid_skull"]),
                note=(row["note"] or "").strip() or None,
                citation=(row["citation"] or "").strip() or None,
            )
            for row in csv.DictReader(handle)
        ]
    validate_backbone(rows)
    return rows


def validate_backbone(rows: list[BackboneRow]) -> None:
    """One root, known parents, no cycles, anchors and groups only on leaves."""
    names = [row.name for row in rows]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise PhylogenyBuildError(f"duplicate backbone names: {duplicates}")
    by_name = {row.name: row for row in rows}
    roots = [row.name for row in rows if row.parent is None]
    if len(roots) != 1:
        raise PhylogenyBuildError(f"backbone needs exactly one root, found {roots}")
    unknown = [row.name for row in rows if row.parent and row.parent not in by_name]
    if unknown:
        raise PhylogenyBuildError(f"backbone rows with unknown parent: {unknown}")
    for row in rows:
        seen = {row.name}
        current = row.parent
        while current is not None:
            if current in seen:
                raise PhylogenyBuildError(f"backbone cycle through {row.name}")
            seen.add(current)
            current = by_name[current].parent
    has_children = {row.parent for row in rows if row.parent}
    for row in rows:
        if row.anchor_families and len(row.anchor_families) < 2:
            raise PhylogenyBuildError(
                f"{row.name}: an anchor needs at least two families to define a clade"
            )
        if row.anchor_families and row.collapsed_group:
            raise PhylogenyBuildError(f"{row.name}: cannot be both anchor and group")
        is_leaf = row.name not in has_children
        if bool(row.anchor_families or row.collapsed_group) != is_leaf:
            raise PhylogenyBuildError(
                f"{row.name}: backbone leaves must be an anchor or a collapsed group, "
                "and only leaves may be"
            )
    for row in rows:
        if row.name in has_children and sum(r.parent == row.name for r in rows) < 2:
            raise PhylogenyBuildError(f"{row.name}: internal backbone nodes need two children")


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def assemble(
    subtree: dict[str, Any],
    crossref_rows: list[dict[str, str]],
    placement: dict[str, FamilyPlacement],
    backbone: list[BackboneRow],
) -> list[PhyloRecord]:
    broken = subtree.get("broken") or {}
    if broken:
        raise PhylogenyBuildError(
            f"species not present as nodes in the synthetic tree: {broken}"
        )

    root = collapse(newick.parse(subtree["newick"]))
    parents = _parent_map(root)
    tips = root.tips()

    species_by_ott = {int(float(r["ott_id"])): r for r in crossref_rows}
    tip_by_ott: dict[int, Clade] = {}
    for tip in tips:
        ott = int(tip.node_id.removeprefix("ott")) if tip.node_id.startswith("ott") else None
        if ott is None or ott not in species_by_ott:
            raise PhylogenyBuildError(
                f"unexpected tip in Open Tree output: {tip.node_id} (if the species "
                "CSV changed, re-run the pipeline with --refresh-opentree)"
            )
        if ott in tip_by_ott:
            raise PhylogenyBuildError(f"species appears twice in subtree: ott{ott}")
        tip_by_ott[ott] = tip
    missing = sorted(set(species_by_ott) - set(tip_by_ott))
    if missing:
        raise PhylogenyBuildError(
            f"species missing from subtree: {missing} (if the species CSV changed, "
            "re-run the pipeline with --refresh-opentree)"
        )

    family_of_tip = {id(tip_by_ott[o]): species_by_ott[o]["family"].strip() for o in tip_by_ott}
    tips_by_family: dict[str, list[Clade]] = {}
    for tip in tips:
        tips_by_family.setdefault(family_of_tip[id(tip)], []).append(tip)

    # Resolve each anchor to its Open Tree clade.
    anchors: dict[str, Clade] = {}
    for row in backbone:
        if not row.anchor_families:
            continue
        unknown = [f for f in row.anchor_families if f not in tips_by_family]
        if unknown:
            raise PhylogenyBuildError(f"{row.name}: anchor families not in data: {unknown}")
        members = [t for f in row.anchor_families for t in tips_by_family[f]]
        anchors[row.name] = mrca(members, parents)

    # Anchors must partition the tips: none overlap, none left out.
    owner: dict[int, str] = {}
    for name, clade in anchors.items():
        for tip in clade.tips():
            if id(tip) in owner:
                raise PhylogenyBuildError(
                    f"anchors {owner[id(tip)]} and {name} overlap at {family_of_tip[id(tip)]}"
                )
            owner[id(tip)] = name
    orphans = sorted(family_of_tip[id(t)] for t in tips if id(t) not in owner)
    if orphans:
        raise PhylogenyBuildError(f"families outside every backbone anchor: {orphans}")

    _check_backbone_agrees(backbone, anchors, parents)

    records: list[PhyloRecord] = []
    by_name = {row.name: row for row in backbone}
    children_of: dict[str | None, list[BackboneRow]] = {}
    for row in backbone:
        children_of.setdefault(row.parent, []).append(row)

    def emit_backbone(row: BackboneRow, parent_key: str | None) -> None:
        common = dict(
            label=row.name,
            parent_key=parent_key,
            extinct=row.extinct,
            collapsed_group=row.collapsed_group,
            placement_uncertain=row.placement_uncertain,
            anapsid_skull=row.anapsid_skull,
            note=row.note,
            citation=row.citation,
        )
        if row.name in anchors:
            clade = anchors[row.name]
            key = clade.node_id
            records.append(
                PhyloRecord(key=key, source=SOURCE_OPENTREE, external_id=clade.node_id, **common)
            )
            for child in clade.children:
                emit_opentree(child, key)
            return
        key = f"backbone:{row.name}"
        records.append(PhyloRecord(key=key, source=SOURCE_BACKBONE, **common))
        for child in children_of.get(row.name, []):
            emit_backbone(child, key)

    def emit_opentree(clade: Clade, parent_key: str) -> None:
        if clade.is_tip:
            family = family_of_tip[id(clade)]
            placed = placement.get(family, _UNPLACED)
            records.append(
                PhyloRecord(
                    key=clade.node_id,
                    parent_key=parent_key,
                    label=family,
                    source=SOURCE_OPENTREE,
                    external_id=clade.node_id,
                    species_ott_id=int(clade.node_id.removeprefix("ott")),
                    family=family,
                    family_ott_id=placed.ott_id,
                    placement_status=placed.status,
                    note=placed.note,
                )
            )
            return
        # Tips already stand for families. An internal node carrying one of our
        # family names (Open Tree's broader definition, e.g. Typhlopidae holding
        # Xenotyphlopidae) would read as a second copy of that family.
        label = None if clade.name in tips_by_family else clade.name
        records.append(
            PhyloRecord(
                key=clade.node_id,
                parent_key=parent_key,
                label=label,
                source=SOURCE_OPENTREE,
                external_id=clade.node_id,
            )
        )
        for child in clade.children:
            emit_opentree(child, clade.node_id)

    root_row = next(row for row in backbone if row.parent is None)
    emit_backbone(by_name[root_row.name], None)

    keys = [r.key for r in records]
    if len(keys) != len(set(keys)):
        raise PhylogenyBuildError("duplicate node keys in assembled tree")
    return records


def _check_backbone_agrees(
    backbone: list[BackboneRow],
    anchors: dict[str, Clade],
    parents: dict[int, Clade | None],
) -> None:
    """Every backbone grouping of 2+ anchors must also be a group in Open Tree."""
    children_of: dict[str, list[str]] = {}
    for row in backbone:
        if row.parent:
            children_of.setdefault(row.parent, []).append(row.name)

    def anchors_under(name: str) -> list[str]:
        if name in anchors:
            return [name]
        return [a for child in children_of.get(name, []) for a in anchors_under(child)]

    for row in backbone:
        below = anchors_under(row.name)
        if len(below) < 2:
            continue
        expected = {id(t) for a in below for t in anchors[a].tips()}
        joined = mrca([anchors[a] for a in below], parents)
        actual = {id(t) for t in joined.tips()}
        if actual != expected:
            intruders = sorted(
                a for a in anchors if a not in below and any(id(t) in actual for t in anchors[a].tips())
            )
            raise PhylogenyBuildError(
                f"backbone groups {below} as {row.name}, but in Open Tree their common "
                f"ancestor also contains {intruders}"
            )


@dataclass
class CladeName:
    name: str
    family_a: str
    family_b: str
    citation: str


def load_clade_names(path: Path) -> list[CladeName]:
    """data/curated/clade_names.csv: names for well-known clades Open Tree leaves
    unnamed, each defined as the common ancestor of two families."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = [
            CladeName(r["name"].strip(), r["family_a"].strip(), r["family_b"].strip(), (r["citation"] or "").strip())
            for r in csv.DictReader(handle)
        ]
    missing = [r.name for r in rows if not r.citation]
    if missing:
        raise PhylogenyBuildError(f"clade names without a citation: {missing}")
    return rows


def apply_clade_names(records: list[PhyloRecord], names: list[CladeName]) -> None:
    """Label the common ancestor of each pair of families. Fails rather than
    renaming a node that already has a different name, or naming a node twice."""
    by_key = {r.key: r for r in records}
    tip_of = {r.family: r.key for r in records if r.family}

    def ancestors(key: str) -> list[str]:
        out = []
        while key is not None:
            out.append(key)
            key = by_key[key].parent_key
        return out

    named: dict[str, str] = {}
    for clade in names:
        missing = [f for f in (clade.family_a, clade.family_b) if f not in tip_of]
        if missing:
            raise PhylogenyBuildError(f"{clade.name}: families not in the tree: {missing}")
        above_b = set(ancestors(tip_of[clade.family_b]))
        node = next(k for k in ancestors(tip_of[clade.family_a]) if k in above_b)
        rec = by_key[node]
        if rec.source != SOURCE_OPENTREE or rec.species_ott_id is not None:
            raise PhylogenyBuildError(f"{clade.name}: lands on {rec.label or node}, not an Open Tree clade")
        if node in named:
            raise PhylogenyBuildError(f"{clade.name} and {named[node]} name the same node")
        if rec.label and rec.label != clade.name:
            raise PhylogenyBuildError(f"{clade.name}: that node is already named {rec.label}")
        rec.label = clade.name
        rec.citation = clade.citation
        named[node] = clade.name


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run the Open Tree extract first")
    return json.loads(path.read_text(encoding="utf-8"))


def run(
    crossref_csv: Path,
    placement: dict[str, FamilyPlacement],
    raw_dir: Path = OPENTREE_RAW_DIR,
    backbone_csv: Path = BACKBONE_PATH,
    clade_names_csv: Path = CLADE_NAMES_PATH,
) -> PhylogenyBuild:
    """Build load-ready records from the cached Open Tree extract.

    ``placement`` comes from etl.transform.family_check.run.
    """
    records = assemble(
        subtree=_read_json(raw_dir / SUBTREE_FILE),
        crossref_rows=read_crossref(crossref_csv),
        placement=placement,
        backbone=load_backbone(backbone_csv),
    )
    apply_clade_names(records, load_clade_names(clade_names_csv))
    synth_id = _read_json(raw_dir / ABOUT_FILE).get("synth_id", "")
    logger.info("build_phylogeny: %d nodes from %s", len(records), synth_id)
    return PhylogenyBuild(records=records, synth_id=synth_id)
