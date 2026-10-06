"""Whole-family check: does each family form one branch in Open Tree's tree?

Family membership comes from The Reptile Database checklist (every species it
assigns to the family). Placement comes from Open Tree's synthetic tree under
each living backbone group (Lepidosauria, Testudines, Crocodylia).

For each family:

  confirmed  every member species in the tree sits on one branch that holds no
             species of any other family.
  flagged    the members do not form one branch. We then find the family's
             *main branch*: the node with the most members and fewest outsiders
             (score = members - outsiders), and report how many members fall
             outside it and which other families intrude into it.
  unknown    none of the family's species are in the tree, or the family name is
             not in the checklist.

Only evidence counts. Open Tree attaches a species with no DNA data wherever its
own (sometimes older) taxonomy files it, so such a species can land "outside"
its family without any study saying so. Every species that would cause a flag
is therefore looked up: if no published tree contains it, it is set aside and
the family is judged again. The note says how many were set aside.

data/curated/family_status_overrides.csv can then set a status by hand where
Open Tree's evidence is known to be outdated; each override needs a reason and
a citation, and both are stated in the note.

`representative_in_main_branch` says whether our representative species sits on
the main branch. If it does not, the family's position in our tree reflects a
stray member rather than the family, and the representative should be swapped.
`representative_trees` counts the published trees that contain it; zero means
Open Tree places it by taxonomy alone, which is also a reason to swap.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from etl.config import FAMILY_OVERRIDES_PATH, OPENTREE_RAW_DIR
from etl.extract import reptiledb
from etl.extract.opentree import (
    CHECKLIST_MATCHES_FILE,
    FAMILY_TNRS_FILE,
    GROUP_SUBTREES_FILE,
    PublishedTrees,
    best_family_match,
    read_crossref,
)
from etl.transform import newick
from etl.transform.build_phylogeny import (
    STATUS_CONFIRMED,
    STATUS_FLAGGED,
    STATUS_UNKNOWN,
    FamilyPlacement,
    parse_label,
)

EXAMPLES = 3  # species / families named in a note
MAX_PASSES = 4  # re-judge a family after setting aside taxonomy-only species


@dataclass
class FamilyCheck:
    family: str
    status: str
    note: str
    checklist_species: int = 0
    species_in_tree: int = 0
    main_branch_members: int = 0
    main_branch_outsiders: int = 0
    representative_in_main_branch: bool | None = None
    representative_trees: int | None = None  # published trees containing it
    main_branch_species: list[str] = field(default_factory=list)
    taxonomy_only_set_aside: int = 0
    override: str | None = None  # reason, when the status was set by hand


class _Forest:
    """All group subtrees as flat arrays, in preorder."""

    def __init__(self, newicks: list[str]) -> None:
        self.parent: list[int] = []
        # OTT id of every node that is a named taxon. A species with subspecies
        # is an internal node (its subspecies are the tips), so species are
        # looked up among all nodes, not just tips.
        self.ott: list[int | None] = []
        for text in newicks:
            stack = [(newick.parse(text), -1)]
            while stack:
                node, parent = stack.pop()
                index = len(self.parent)
                self.parent.append(parent)
                _, node_id = parse_label(node.label)
                self.ott.append(int(node_id[3:]) if node_id and node_id.startswith("ott") else None)
                stack.extend((child, index) for child in reversed(node.children))
        self.tip_index = {o: i for i, o in enumerate(self.ott) if o is not None}
        # In preorder every subtree is a contiguous block: [i, i + size[i]).
        self.size = [1] * len(self.parent)
        for i in range(len(self.parent) - 1, 0, -1):
            if self.parent[i] != -1:
                self.size[self.parent[i]] += self.size[i]

    def is_under(self, index: int, ancestor: int) -> bool:
        return ancestor <= index < ancestor + self.size[ancestor]


def _family_of_ott(checklist: pd.DataFrame, matches: dict[str, dict]) -> tuple[dict[int, str], dict[int, str]]:
    """OTT id -> checklist family and -> species name. An OTT id claimed by two
    families (name collisions) is left out rather than guessed."""
    family: dict[int, str] = {}
    name: dict[int, str] = {}
    clashes: set[int] = set()
    for species, fam in zip(checklist["species"], checklist["family"]):
        match = matches.get(species)
        if match is None:
            continue
        ott = match["ott_id"]
        if ott in family and family[ott] != fam:
            clashes.add(ott)
        family[ott] = fam
        name.setdefault(ott, species)
    for ott in clashes:
        family.pop(ott, None)
    return family, name


def check_families(
    group_newicks: list[str],
    checklist: pd.DataFrame,
    matches: dict[str, dict],
    representatives: dict[str, int],
    checklist_label: str = "The Reptile Database",
    published_trees: Callable[[int], list[str]] | None = None,
) -> dict[str, FamilyCheck]:
    """``representatives``: family -> OTT id of its representative species.

    ``published_trees``: OTT id -> published trees containing that species. When
    given, species that would flag a family but are in no published tree are
    set aside (see module docstring). Without it every placement counts.
    """
    forest = _Forest(group_newicks)
    family_of, name_of = _family_of_ott(checklist, matches)
    in_checklist = Counter(checklist["family"])

    results: dict[str, FamilyCheck] = {}
    for fam, rep_ott in representatives.items():
        total = in_checklist.get(fam, 0)
        if total == 0:
            results[fam] = FamilyCheck(fam, STATUS_UNKNOWN, f"Not a family in {checklist_label}.")
            continue
        set_aside: set[int] = set()
        checked: set[int] = set()
        for _ in range(MAX_PASSES):
            check, suspects = _judge(
                forest, family_of, name_of, fam, rep_ott, total, checklist_label, set_aside
            )
            if published_trees is None or check.status != STATUS_FLAGGED:
                break
            new = [o for o in suspects if o not in checked]
            checked.update(new)
            found = {o for o in new if not published_trees(o)}
            if not found:
                break
            set_aside |= found
        if set_aside:
            check.taxonomy_only_set_aside = len(set_aside)
            verb = "was" if len(set_aside) == 1 else "were"
            check.note += (
                f" {len(set_aside)} species that Open Tree places by taxonomy alone "
                f"(in no published tree) {verb} not counted."
            )
        results[fam] = check
    return results


def _judge(
    forest: _Forest,
    family_of: dict[int, str],
    name_of: dict[int, str],
    fam: str,
    rep_ott: int,
    total: int,
    checklist_label: str,
    set_aside: set[int],
) -> tuple[FamilyCheck, list[int]]:
    """Judge one family, ignoring ``set_aside`` species. Returns the result and
    the species responsible for any flag (members outside the main branch and
    other families' species inside it)."""
    n = len(forest.parent)
    members = [
        i for o, i in forest.tip_index.items() if family_of.get(o) == fam and o not in set_aside
    ]
    if not members:
        return FamilyCheck(
            fam, STATUS_UNKNOWN,
            f"None of its {total} species ({checklist_label}) are in Open Tree's tree.",
            checklist_species=total,
        ), []

    inside = [0] * n
    outside = [0] * n
    for i in members:
        inside[i] = 1
    for o, i in forest.tip_index.items():
        other = family_of.get(o)
        if other is not None and other != fam and o not in set_aside:
            outside[i] = 1
    for i in range(n - 1, -1, -1):  # children before parents (preorder reversed)
        p = forest.parent[i]
        if p != -1:
            inside[p] += inside[i]
            outside[p] += outside[i]

    def outsiders_under(node: int) -> list[int]:
        return [
            forest.ott[i] for i in range(node, node + forest.size[node])
            if forest.ott[i] in family_of and family_of[forest.ott[i]] != fam
            and forest.ott[i] not in set_aside
        ]

    def named_families(otts: list[int]) -> str:
        counts = Counter(family_of[o] for o in otts).most_common(EXAMPLES)
        return ", ".join(f"{f} ({c})" for f, c in counts)

    m = len(members)
    rep_index = forest.tip_index.get(rep_ott)
    check = FamilyCheck(fam, STATUS_CONFIRMED, "", checklist_species=total, species_in_tree=m)
    mrca = max((i for i in range(n) if inside[i] == m), default=None)  # deepest node holding all
    if mrca is not None and outside[mrca] == 0:
        check.main_branch_members, check.main_branch_outsiders = m, 0
        check.representative_in_main_branch = None if rep_index is None else forest.is_under(rep_index, mrca)
        check.main_branch_species = sorted(name_of[forest.ott[i]] for i in members)
        check.note = (
            f"All {m} of its species in Open Tree's tree form one branch "
            f"({total} species in {checklist_label})."
            if m > 1 else
            f"Its only species in Open Tree's tree ({total} in {checklist_label}) "
            "is a single branch by definition."
        )
        return check, []

    check.status = STATUS_FLAGGED
    # Main branch: holds a majority of the family and more members than
    # outsiders; best members-minus-outsiders, then the smallest such node.
    majority = max(2, -(-m // 2))
    candidates = [i for i in range(n) if inside[i] >= majority and inside[i] > outside[i]]
    if not candidates:
        intruder_otts = outsiders_under(mrca if mrca is not None else 0)
        check.note = (
            f"Not a branch in Open Tree: its {m} species are spread among other families "
            f"({named_families(intruder_otts)}), so no single branch stands for the family. "
            f"Membership from {checklist_label}."
        )
        return check, [forest.ott[i] for i in members] + intruder_otts

    best = max(candidates, key=lambda i: (inside[i] - outside[i], -(inside[i] + outside[i])))
    check.main_branch_members, check.main_branch_outsiders = inside[best], outside[best]
    check.representative_in_main_branch = None if rep_index is None else forest.is_under(rep_index, best)
    check.main_branch_species = sorted(name_of[forest.ott[i]] for i in members if forest.is_under(i, best))
    stray_otts = [forest.ott[i] for i in members if not forest.is_under(i, best)]
    intruder_otts = outsiders_under(best)
    strays = sorted(name_of[o] for o in stray_otts)
    parts = [f"Not one branch in Open Tree: {inside[best]} of its {m} species form the main branch"]
    if intruder_otts:
        parts.append(
            f"with {len(intruder_otts)} species of other families inside it ({named_families(intruder_otts)})"
        )
    if strays:
        verb = "sits" if len(strays) == 1 else "sit"
        parts.append(f"{len(strays)} {verb} elsewhere (e.g. {', '.join(strays[:EXAMPLES])})")
    check.note = "; ".join(parts) + f". Membership from {checklist_label}."
    if check.representative_in_main_branch is False:
        check.note += " The representative species is outside the main branch."
    return check, stray_otts + intruder_otts


@dataclass
class FamilyOverride:
    family: str
    status: str
    reason: str
    citation: str


def load_overrides(path: Path) -> dict[str, FamilyOverride]:
    """data/curated/family_status_overrides.csv: family,status,reason,citation."""
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    out: dict[str, FamilyOverride] = {}
    for row in rows:
        fam = row["family"].strip()
        status = row["status"].strip()
        if status not in {STATUS_CONFIRMED, STATUS_FLAGGED, STATUS_UNKNOWN}:
            raise ValueError(f"{fam}: override status {status!r} is not a placement status")
        reason, citation = (row.get("reason") or "").strip(), (row.get("citation") or "").strip()
        if not reason or not citation:
            raise ValueError(f"{fam}: an override needs a reason and a citation")
        if fam in out:
            raise ValueError(f"duplicate override for {fam}")
        out[fam] = FamilyOverride(fam, status, reason, citation)
    return out


def apply_overrides(checks: dict[str, FamilyCheck], overrides: dict[str, FamilyOverride]) -> list[str]:
    """Apply hand-set statuses. Returns the families whose override changed
    nothing (the computed status already matches), so they can be retired."""
    unknown = sorted(set(overrides) - set(checks))
    if unknown:
        raise ValueError(f"overrides for families not in the data: {unknown}")
    stale = []
    for fam, override in overrides.items():
        check = checks[fam]
        if check.status == override.status:
            stale.append(fam)
            continue
        check.note += f" Status set to {override.status} by hand: {override.reason} ({override.citation})."
        check.status = override.status
        check.override = override.reason
    return stale


def _read_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run the Open Tree extract first")
    return json.loads(path.read_text(encoding="utf-8"))


def run(
    crossref_csv: Path,
    raw_dir: Path = OPENTREE_RAW_DIR,
    overrides_csv: Path = FAMILY_OVERRIDES_PATH,
) -> tuple[dict[str, FamilyPlacement], dict[str, FamilyCheck], list[str]]:
    """Check every family in ``crossref_csv`` against the cached extracts.

    Returns the placements the tree build needs (family -> status + note), the
    full results for reporting, and any overrides that are no longer needed.
    Species lookups not yet cached hit Open Tree and are saved.
    """
    rows = read_crossref(crossref_csv)
    representatives = {row["family"].strip(): int(float(row["ott_id"])) for row in rows}
    checklist = reptiledb.read_checklist(reptiledb.checklist_path())
    label = f"The Reptile Database, {reptiledb.release_of(reptiledb.checklist_path().name)} release"
    support = PublishedTrees(raw_dir)
    try:
        checks = check_families(
            [g["newick"] for g in _read_json(raw_dir / GROUP_SUBTREES_FILE).values()],
            checklist,
            _read_json(raw_dir / CHECKLIST_MATCHES_FILE),
            representatives,
            checklist_label=label,
            published_trees=support,
        )
        for fam, check in checks.items():
            check.representative_trees = len(support(representatives[fam]))
    finally:
        support.save()  # keep lookups made so far
    stale = apply_overrides(checks, load_overrides(overrides_csv))
    for check in checks.values():
        if check.representative_trees == 0:
            check.note += (
                " Its representative species is in no published tree in Open Tree, "
                "so its position comes from taxonomy alone."
            )
    family_ott = {
        r["name"]: (best_family_match(r) or {}).get("ott_id")
        for r in _read_json(raw_dir / FAMILY_TNRS_FILE).get("results", [])
    }
    placement = {
        fam: FamilyPlacement(ott_id=family_ott.get(fam), status=c.status, note=c.note)
        for fam, c in checks.items()
    }
    return placement, checks, stale
