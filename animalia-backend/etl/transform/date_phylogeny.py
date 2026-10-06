"""Give every node of the assembled phylogeny an age in millions of years (Ma).

Sources, in order of precedence:

  present            living family tips and living groups (Aves) sit at 0 Ma.
  last appearance    extinct groups (data/curated/fossil_dates.csv) end at their
                     last fossil; their first fossil is kept alongside.
  fossil minimum     backbone nodes only fossils can date (Reptilia, Dinosauria,
                     ...) take the curated minimum age from the oldest fossil.
  TimeTree 5         every other branch point: the median published molecular
                     estimate for the split between one taxon on each side.
  interpolated       a branch point TimeTree cannot date is placed halfway
                     between its parent and its oldest dated descendant.

Then consistency: an ancestor can never be younger than a descendant (or than
the first fossil of an extinct descendant).

  - Two TimeTree estimates whose confidence intervals do not overlap: a real
    conflict. The one backed by fewer studies is discarded and that node is
    interpolated instead, so one weak outlier cannot drag a chain of
    better-supported ancestors with it.
  - Everything else (estimates within each other's uncertainty, or a clash with
    a fossil, which is a hard minimum): the ancestor is raised to meet it.

Either way `age_adjusted` is set and the original estimate is kept in
`age_unadjusted_ma`.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Protocol

from etl.config import BACKBONE_PATH, FOSSIL_DATES_PATH, OPENTREE_RAW_DIR
from etl.extract.opentree import (
    FAMILY_TNRS_FILE,
    GROUP_TNRS_FILE,
    SPECIES_TNRS_FILE,
    best_family_match,
    ncbi_id,
)
from etl.extract.timetree import DivergenceEstimate
from etl.transform.build_phylogeny import (
    STATUS_CONFIRMED,
    BackboneRow,
    PhylogenyBuild,
    PhyloRecord,
    load_backbone,
)

logger = logging.getLogger(__name__)

AGE_PRESENT = "present"
AGE_LAST_APPEARANCE = "last appearance"
AGE_FOSSIL_MINIMUM = "fossil minimum"
AGE_TIMETREE = "TimeTree 5"
AGE_INTERPOLATED = "interpolated"

TIMETREE_CITATION = "Kumar et al. 2022, Mol Biol Evol 39:msac174 (TimeTree 5)"
MAX_AGE_MA = 400.0
IDS_PER_CHILD = 4       # taxa tried from each side of a split
MAX_ATTEMPTS = 12       # TimeTree queries per branch point before giving up


class DatingError(ValueError):
    """The curated dates or the dated tree are inconsistent."""


class DivergenceSource(Protocol):
    def divergence(self, a: int, b: int) -> DivergenceEstimate | None: ...


@dataclass
class FossilDate:
    name: str
    node_min_age_ma: float | None
    first_appearance_ma: float | None
    last_appearance_ma: float | None
    pbdb_name: str | None
    citation: str
    note: str | None


@dataclass
class DatingReport:
    by_source: dict[str, int] = field(default_factory=dict)
    discarded: list[tuple[str, float]] = field(default_factory=list)       # (node, estimate)
    adjusted: list[tuple[str, float, float]] = field(default_factory=list)  # (node, from, to)
    interpolated: list[str] = field(default_factory=list)
    timetree_queries: int = 0


# --------------------------------------------------------------------------- #
# Curated fossil dates
# --------------------------------------------------------------------------- #


def _age(value: str | None, name: str, column: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    age = float(text)
    if not 0 <= age <= MAX_AGE_MA:
        raise DatingError(f"{name}: {column}={age} is outside 0-{MAX_AGE_MA} Ma")
    return age


def load_fossil_dates(
    path: Path, backbone: list[BackboneRow], clade_names: frozenset[str] = frozenset()
) -> dict[str, FossilDate]:
    """``clade_names``: named internal Open Tree nodes (e.g. Squamata) that may
    also take a fossil minimum age."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    dates: dict[str, FossilDate] = {}
    for row in rows:
        name = row["name"].strip()
        if name in dates:
            raise DatingError(f"duplicate fossil date row: {name}")
        citation = (row["citation"] or "").strip()
        if not citation:
            raise DatingError(f"{name}: fossil date has no citation")
        dates[name] = FossilDate(
            name=name,
            node_min_age_ma=_age(row["node_min_age_ma"], name, "node_min_age_ma"),
            first_appearance_ma=_age(row["first_appearance_ma"], name, "first_appearance_ma"),
            last_appearance_ma=_age(row["last_appearance_ma"], name, "last_appearance_ma"),
            pbdb_name=(row["pbdb_name"] or "").strip() or None,
            citation=citation,
            note=(row["note"] or "").strip() or None,
        )
    validate_fossil_dates(dates, backbone, clade_names)
    return dates


def validate_fossil_dates(
    dates: dict[str, FossilDate],
    backbone: list[BackboneRow],
    clade_names: frozenset[str] = frozenset(),
) -> None:
    """Each kind of node takes exactly the kind of date that fits it. A named
    Open Tree clade (not in the backbone) can only take a fossil minimum age."""
    rows = {row.name: row for row in backbone}
    has_children = {row.parent for row in backbone if row.parent}
    unknown = sorted(set(dates) - set(rows) - set(clade_names))
    if unknown:
        raise DatingError(f"fossil dates for names not in the tree: {unknown}")
    for name in sorted((set(dates) & set(clade_names)) - set(rows)):
        date = dates[name]
        if date.node_min_age_ma is None or date.first_appearance_ma or date.last_appearance_ma:
            raise DatingError(f"{name}: a clade takes node_min_age_ma only")
    for row in backbone:
        date = dates.get(row.name)
        if row.collapsed_group and row.extinct:
            if date is None or date.first_appearance_ma is None or date.last_appearance_ma is None:
                raise DatingError(f"{row.name}: extinct group needs first and last appearance")
        if date is None:
            continue
        if row.anchor_families:
            raise DatingError(f"{row.name}: living groups are dated by TimeTree, not fossil_dates")
        if row.name in has_children:
            if date.node_min_age_ma is None or date.first_appearance_ma or date.last_appearance_ma:
                raise DatingError(f"{row.name}: an internal node takes node_min_age_ma only")
        else:
            if date.node_min_age_ma is not None:
                raise DatingError(f"{row.name}: a tip takes appearance dates, not node_min_age_ma")
            if not row.extinct and date.last_appearance_ma is not None:
                raise DatingError(f"{row.name}: a living group has no last appearance")
        first, last = date.first_appearance_ma, date.last_appearance_ma
        if first is not None and last is not None and last > first:
            raise DatingError(f"{row.name}: last appearance {last} is older than first {first}")


# --------------------------------------------------------------------------- #
# NCBI ids used to ask TimeTree about a split
# --------------------------------------------------------------------------- #


def dating_ids(
    records: list[PhyloRecord],
    species_tnrs: dict[str, Any],
    family_tnrs: dict[str, Any],
    group_tnrs: dict[str, Any],
) -> dict[str, list[int]]:
    """Tip key -> NCBI ids to try, best first.

    A confirmed family is asked about as a whole family first. A flagged or
    unknown family may not be one branch, so its own species goes first.
    """
    species_ncbi: dict[int, int] = {}
    for result in species_tnrs.get("results", []):
        for match in result.get("matches", []):
            taxon = match.get("taxon", {})
            ncbi = ncbi_id(taxon)
            if ncbi is not None and taxon.get("ott_id") is not None:
                species_ncbi.setdefault(taxon["ott_id"], ncbi)
    family_ncbi = {
        r["name"]: ncbi_id(best_family_match(r)) for r in family_tnrs.get("results", [])
    }
    group_ncbi: dict[str, int | None] = {}
    for result in group_tnrs.get("results", []):
        exact = [
            m for m in result.get("matches", [])
            if m.get("score") == 1.0 and not m.get("is_synonym")
        ]
        group_ncbi[result["name"]] = ncbi_id(exact[0]["taxon"]) if exact else None

    out: dict[str, list[int]] = {}
    for rec in records:
        if rec.species_ott_id is not None:
            fam = family_ncbi.get(rec.family or "")
            sp = species_ncbi.get(rec.species_ott_id)
            ordered = [fam, sp] if rec.placement_status == STATUS_CONFIRMED else [sp, fam]
            out[rec.key] = list(dict.fromkeys(i for i in ordered if i is not None))
        elif rec.collapsed_group and not rec.extinct:
            ncbi = group_ncbi.get(rec.label or "")
            out[rec.key] = [ncbi] if ncbi is not None else []
    return out


# --------------------------------------------------------------------------- #
# Dating
# --------------------------------------------------------------------------- #


class _Tree:
    def __init__(self, records: list[PhyloRecord]) -> None:
        self.by_key = {r.key: r for r in records}
        self.children: dict[str, list[str]] = {r.key: [] for r in records}
        for r in records:
            if r.parent_key is not None:
                self.children[r.parent_key].append(r.key)
        roots = [r.key for r in records if r.parent_key is None]
        if len(roots) != 1:
            raise DatingError(f"expected one root, found {roots}")
        self.root = roots[0]

    def preorder(self) -> list[str]:
        out, stack = [], [self.root]
        while stack:
            key = stack.pop()
            out.append(key)
            stack.extend(reversed(self.children[key]))
        return out

    def describe(self, key: str) -> str:
        """A readable name: the label, or 'ancestor of A + B' for unnamed nodes."""
        rec = self.by_key[key]
        if rec.label:
            return rec.label
        firsts = [self.by_key[self.tips_under(c)[0]].label for c in self.children[key][:2]]
        return "ancestor of " + " + ".join(str(f) for f in firsts)

    def tips_under(self, key: str) -> list[str]:
        return [k for k in self._subtree(key) if not self.children[k]]

    def _subtree(self, key: str) -> list[str]:
        out, stack = [], [key]
        while stack:
            k = stack.pop()
            out.append(k)
            stack.extend(reversed(self.children[k]))
        return out


def _side_ids(tree: _Tree, key: str, ids: dict[str, list[int]]) -> list[int]:
    """Up to IDS_PER_CHILD ids from one side of a split: each tip's best id first."""
    per_tip = [ids.get(tip, []) for tip in tree.tips_under(key)]
    ordered: list[int] = []
    for rank in range(max((len(p) for p in per_tip), default=0)):
        ordered.extend(p[rank] for p in per_tip if len(p) > rank)
    return list(dict.fromkeys(ordered))[:IDS_PER_CHILD]


def date_records(
    records: list[PhyloRecord],
    fossil: dict[str, FossilDate],
    ids: dict[str, list[int]],
    timetree: DivergenceSource,
) -> DatingReport:
    """Fill the age fields of ``records`` in place."""
    tree = _Tree(records)
    report = DatingReport()

    # 1. Tips and fossil-dated nodes (backbone groups, or named clades inside
    #    Open Tree's part such as Squamata; never an Open Tree family tip).
    for key in tree.preorder():
        rec = tree.by_key[key]
        fossil_eligible = rec.source == "curated_backbone" or bool(tree.children[key])
        date = fossil.get(rec.label or "") if fossil_eligible else None
        if not tree.children[key]:
            if date is not None:
                rec.first_appearance_ma = date.first_appearance_ma
                rec.last_appearance_ma = date.last_appearance_ma
                rec.age_citation = date.citation
            if rec.extinct:
                rec.age_ma, rec.age_source = rec.last_appearance_ma, AGE_LAST_APPEARANCE
            else:
                rec.age_ma, rec.age_source = 0.0, AGE_PRESENT
        elif date is not None:
            rec.age_ma, rec.age_source = date.node_min_age_ma, AGE_FOSSIL_MINIMUM
            rec.age_citation = date.citation

    # 2. TimeTree for every other branch point.
    for key in tree.preorder():
        rec = tree.by_key[key]
        if not tree.children[key] or rec.age_ma is not None:
            continue
        sides = [_side_ids(tree, child, ids) for child in tree.children[key]]
        estimate = None
        attempts = 0
        for left, right in combinations(sides, 2):
            for a in left:
                for b in right:
                    if estimate is not None or attempts >= MAX_ATTEMPTS:
                        break
                    attempts += 1
                    estimate = timetree.divergence(a, b)
        report.timetree_queries += attempts
        if estimate is not None:
            rec.age_ma = estimate.age_ma
            rec.age_ci_low, rec.age_ci_high = estimate.ci_low, estimate.ci_high
            rec.age_study_count = estimate.study_count
            rec.age_source, rec.age_citation = AGE_TIMETREE, TIMETREE_CITATION

    # 3a. TimeTree vs TimeTree: discard the less-supported side of each clash.
    _discard_weaker_timetree_conflicts(tree, report)

    # 3b. Fossils are hard minimums: raise any ancestor that is still too young.
    floor: dict[str, float] = {}
    for key in reversed(tree.preorder()):
        rec = tree.by_key[key]
        if not tree.children[key]:
            floor[key] = rec.first_appearance_ma if rec.first_appearance_ma is not None else rec.age_ma
            continue
        need = max(floor[c] for c in tree.children[key])
        if rec.age_ma is not None and rec.age_ma < need:
            report.adjusted.append((tree.describe(key), rec.age_ma, need))
            rec.age_unadjusted_ma = rec.age_ma
            rec.age_ma = need
            rec.age_adjusted = True
        floor[key] = rec.age_ma if rec.age_ma is not None else need

    # 4. Interpolate whatever TimeTree could not date.
    for key in tree.preorder():
        rec = tree.by_key[key]
        if rec.age_ma is not None:
            continue
        parent = tree.by_key[rec.parent_key] if rec.parent_key else None
        if parent is None:
            raise DatingError("the root has no age; give it a fossil minimum")
        rec.age_ma = (parent.age_ma + floor[key]) / 2
        rec.age_source = AGE_INTERPOLATED
        report.interpolated.append(tree.describe(key))

    for rec in records:
        report.by_source[rec.age_source] = report.by_source.get(rec.age_source, 0) + 1
    return report


def _discard_weaker_timetree_conflicts(tree: _Tree, report: DatingReport) -> None:
    """Repeatedly find TimeTree nodes older than their nearest dated TimeTree
    ancestor, with confidence intervals that do not overlap, and discard
    whichever of the two has fewer supporting studies (the descendant on a
    tie). The worst clash is resolved first. Overlapping clashes are left for
    the raise pass: the two estimates agree within their uncertainty."""

    def intervals_overlap(young: PhyloRecord, old: PhyloRecord) -> bool:
        if young.age_ci_low is None or old.age_ci_high is None:
            return False
        return young.age_ci_low <= old.age_ci_high

    def nearest_dated_ancestor(key: str) -> PhyloRecord | None:
        parent = tree.by_key[key].parent_key
        while parent is not None:
            rec = tree.by_key[parent]
            if rec.age_ma is not None:
                return rec
            parent = rec.parent_key
        return None

    while True:
        worst: tuple[float, PhyloRecord, PhyloRecord] | None = None
        for key in tree.preorder():
            rec = tree.by_key[key]
            if rec.age_source != AGE_TIMETREE:
                continue
            anc = nearest_dated_ancestor(key)
            if anc is None or anc.age_source != AGE_TIMETREE or rec.age_ma <= anc.age_ma:
                continue
            if intervals_overlap(rec, anc):
                continue
            gap = rec.age_ma - anc.age_ma
            if worst is None or gap > worst[0]:
                worst = (gap, rec, anc)
        if worst is None:
            return
        _, child, anc = worst
        loser = anc if (anc.age_study_count or 0) < (child.age_study_count or 0) else child
        report.discarded.append((tree.describe(loser.key), loser.age_ma))
        loser.age_unadjusted_ma = loser.age_ma
        loser.age_adjusted = True
        loser.age_ma = loser.age_ci_low = loser.age_ci_high = None
        loser.age_study_count = None
        loser.age_source = loser.age_citation = None


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run the Open Tree extract first")
    return json.loads(path.read_text(encoding="utf-8"))


def run(
    build: PhylogenyBuild,
    timetree: DivergenceSource,
    raw_dir: Path = OPENTREE_RAW_DIR,
    fossil_csv: Path = FOSSIL_DATES_PATH,
    backbone_csv: Path = BACKBONE_PATH,
) -> DatingReport:
    """Date ``build.records`` in place using cached Open Tree matches + TimeTree."""
    clade_labels = [r.label for r in build.records if r.label and r.species_ott_id is None]
    duplicated = sorted({n for n in clade_labels if clade_labels.count(n) > 1})
    if duplicated:
        raise DatingError(f"clade names used on more than one node: {duplicated}")
    fossil = load_fossil_dates(fossil_csv, load_backbone(backbone_csv), frozenset(clade_labels))
    ids = dating_ids(
        build.records,
        species_tnrs=_read_json(raw_dir / SPECIES_TNRS_FILE),
        family_tnrs=_read_json(raw_dir / FAMILY_TNRS_FILE),
        group_tnrs=_read_json(raw_dir / GROUP_TNRS_FILE),
    )
    report = date_records(build.records, fossil, ids, timetree)
    logger.info("date_phylogeny: %s", report.by_source)
    return report
