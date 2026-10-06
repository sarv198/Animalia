"""Phylogeny ETL + API unit tests. No network, no database."""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routers.phylogeny import build_phylogeny_tree
from etl.extract.opentree import best_family_match
from etl.transform import newick
from etl.transform.build_phylogeny import (
    BackboneRow,
    CladeName,
    PhylogenyBuildError,
    apply_clade_names,
    assemble,
    collapse,
    load_backbone,
    load_clade_names,
    parse_label,
    validate_backbone,
)

ROOT = Path(__file__).resolve().parents[1]

# A small Open Tree-style subtree (label_format=name_and_id). It includes a
# single-child chain (Chelodina), a quoted homonym label (Testudo), an unnamed
# branching node under a named single-child parent (Episquamata), and the
# Open Tree "spine" above the anchors (Sauria, mrcaott6ott8) that the backbone
# replaces.
SUBTREE_NEWICK = (
    "((Sphenodon_punctatus_ott1,"
    "(((Lacerta_viridis_ott2,(Varanus_varius_ott4,Python_regius_ott5)mrcaott4ott5)"
    "mrcaott2ott4)Episquamata_ott110,Gekko_gecko_ott3)Squamata_ott100)Lepidosauria_ott101,"
    "(((Chelodina_longicollis_ott6)Chelodina_ott60,"
    "((Testudo_graeca_ott7)'Testudo (genus in Holozoa) ott70'))Testudines_ott102,"
    "(Alligator_mississippiensis_ott8,Crocodylus_niloticus_ott9)Crocodylia_ott103)mrcaott6ott8)"
    "Sauria_ott104;"
)

CROSSREF = [
    {"species": "Sphenodon punctatus", "family": "Sphenodontidae", "ott_id": "1"},
    {"species": "Lacerta viridis", "family": "Lacertidae", "ott_id": "2"},
    {"species": "Gekko gecko", "family": "Gekkonidae", "ott_id": "3"},
    {"species": "Varanus varius", "family": "Varanidae", "ott_id": "4"},
    {"species": "Python regius", "family": "Pythonidae", "ott_id": "5.0"},
    {"species": "Chelodina longicollis", "family": "Chelidae", "ott_id": "6"},
    {"species": "Testudo graeca", "family": "Testudinidae", "ott_id": "7"},
    {"species": "Alligator mississippiensis", "family": "Alligatoridae", "ott_id": "8"},
    {"species": "Crocodylus niloticus", "family": "Crocodylidae", "ott_id": "9"},
]


def row(name, parent, anchors="", group=False, extinct=False):
    return BackboneRow(
        name=name,
        parent=parent,
        anchor_families=[a for a in anchors.split(";") if a],
        extinct=extinct,
        collapsed_group=group,
        placement_uncertain=False,
        anapsid_skull=False,
        note=None,
        citation=None,
    )


def mini_backbone():
    return [
        row("Reptilia", None),
        row("Mesosauria", "Reptilia", group=True, extinct=True),
        row("Sauria", "Reptilia"),
        row("Lepidosauria", "Sauria", "Sphenodontidae;Lacertidae"),
        row("Archelosauria", "Sauria"),
        row("Testudines", "Archelosauria", "Chelidae;Testudinidae"),
        row("Archosauria", "Archelosauria"),
        row("Crocodylia", "Archosauria", "Alligatoridae;Crocodylidae"),
        row("Aves", "Archosauria", group=True),
    ]


def build(backbone=None, subtree=None, placement=None):
    return assemble(
        subtree=subtree or {"newick": SUBTREE_NEWICK, "broken": {}},
        crossref_rows=CROSSREF,
        placement=placement or {},
        backbone=backbone or mini_backbone(),
    )


def ancestors(records, key):
    parent_of = {r.key: r.parent_key for r in records}
    path = []
    while key is not None:
        path.append(key)
        key = parent_of[key]
    return path


def mrca_depth(records, label_a, label_b):
    """Depth of the common ancestor; larger = more recent = more closely related."""
    key_of = {r.label: r.key for r in records if r.label}
    a = ancestors(records, key_of[label_a])
    b = set(ancestors(records, key_of[label_b]))
    shared = next(k for k in a if k in b)
    return len(ancestors(records, shared))


# --------------------------------------------------------------------------- #
# Newick + labels
# --------------------------------------------------------------------------- #


def test_newick_parses_nesting_quotes_and_lengths() -> None:
    tree = newick.parse("((A_b:0.1,'C''d e':2)X,F)Root;")
    assert tree.label == "Root"
    inner, f = tree.children
    assert inner.label == "X"
    assert [c.label for c in inner.children] == ["A b", "C'd e"]
    assert f.label == "F" and f.children == []


@pytest.mark.parametrize("bad", ["((A,B);", "(A,B));", "('A,B);"])
def test_newick_rejects_malformed(bad: str) -> None:
    with pytest.raises(newick.NewickError):
        newick.parse(bad)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Alligator mississippiensis ott335590", ("Alligator mississippiensis", "ott335590")),
        ("mrcaott246ott31216", (None, "mrcaott246ott31216")),
        ("Pelodiscus (genus in Holozoa) ott85386", ("Pelodiscus", "ott85386")),
        ("Squamata (order in Deuterostomia) ott35881", ("Squamata", "ott35881")),
        (None, (None, None)),
    ],
)
def test_parse_label(label, expected) -> None:
    assert parse_label(label) == expected


def test_collapse_removes_chains_and_borrows_names() -> None:
    root = collapse(newick.parse(SUBTREE_NEWICK))
    tips = {t.node_id for t in root.tips()}
    assert tips == {f"ott{i}" for i in range(1, 10)}  # chain parents gone, species kept
    squamata = root.children[0].children[1]
    episquamata = squamata.children[0]
    assert episquamata.node_id == "mrcaott2ott4"
    assert episquamata.name == "Episquamata"  # borrowed from the single-child parent


# --------------------------------------------------------------------------- #
# Family name matching (Open Tree ids, used for dating)
# --------------------------------------------------------------------------- #


def tnrs_result(name, *matches):
    return {"name": name, "matches": list(matches)}


def match(name, rank, ott_id, synonym=False, score=1.0):
    return {"taxon": {"name": name, "rank": rank, "ott_id": ott_id}, "is_synonym": synonym, "score": score}


def test_best_family_match_accepts_rank_shift_but_not_other_synonyms() -> None:
    shifted = tnrs_result("Crotaphytidae", match("Crotaphytinae", "subfamily", 10, synonym=True))
    assert best_family_match(shifted)["ott_id"] == 10
    unrelated = tnrs_result("Fooidae", match("Barinae", "subfamily", 11, synonym=True))
    assert best_family_match(unrelated) is None
    fuzzy = tnrs_result("Boidae", match("Boidae", "family", 12, score=0.9))
    assert best_family_match(fuzzy) is None


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def test_assemble_grafts_backbone_over_open_tree() -> None:
    records = build()
    assert records[0].label == "Reptilia" and records[0].parent_key is None
    keys = {r.key for r in records}
    assert "ott104" not in keys and "mrcaott6ott8" not in keys  # Open Tree spine replaced
    by_label = {r.label: r for r in records if r.label}
    assert by_label["Testudines"].key == "ott102"  # anchor reuses the Open Tree node
    assert by_label["Testudines"].parent_key == "backbone:Archelosauria"
    assert by_label["Aves"].collapsed_group and not by_label["Aves"].extinct
    assert by_label["Mesosauria"].extinct
    family_tips = [r for r in records if r.family]
    assert len(family_tips) == 9
    assert all(r.placement_status == "unknown" for r in family_tips)  # no placement data given


def test_assemble_has_no_single_child_nodes() -> None:
    records = build()
    counts: dict[str, int] = {}
    for r in records:
        if r.parent_key:
            counts[r.parent_key] = counts.get(r.parent_key, 0) + 1
    assert all(n >= 2 for n in counts.values())


def test_assemble_preserves_relationships() -> None:
    records = build()
    assert mrca_depth(records, "Varanidae", "Pythonidae") > mrca_depth(records, "Varanidae", "Gekkonidae")
    assert mrca_depth(records, "Crocodylidae", "Aves") > mrca_depth(records, "Crocodylidae", "Testudinidae")
    assert mrca_depth(records, "Testudinidae", "Crocodylidae") > mrca_depth(records, "Testudinidae", "Lacertidae")


def test_assemble_rejects_backbone_that_contradicts_open_tree() -> None:
    backbone = [
        row("Reptilia", None),
        row("Wrong", "Reptilia"),  # claims turtles group with lepidosaurs
        row("Lepidosauria", "Wrong", "Sphenodontidae;Lacertidae"),
        row("Testudines", "Wrong", "Chelidae;Testudinidae"),
        row("Crocodylia", "Reptilia", "Alligatoridae;Crocodylidae"),
    ]
    with pytest.raises(PhylogenyBuildError, match="Crocodylia"):
        build(backbone=backbone)


def test_assemble_rejects_families_outside_anchors() -> None:
    backbone = mini_backbone()
    backbone[3] = row("Lepidosauria", "Sauria", "Lacertidae;Varanidae")  # misses tuatara + gecko
    with pytest.raises(PhylogenyBuildError, match="outside every backbone anchor"):
        build(backbone=backbone)


def test_assemble_rejects_broken_species() -> None:
    with pytest.raises(PhylogenyBuildError, match="not present as nodes"):
        build(subtree={"newick": SUBTREE_NEWICK, "broken": {"ott5": "mrcaott4ott5"}})


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([row("A", None, group=True), row("B", None, group=True)], "exactly one root"),
        ([row("A", None), row("B", "A", "Chelidae"), row("C", "A", group=True)], "two families"),
        ([row("A", None), row("B", "A"), row("C", "B", group=True)], "two children"),
        ([row("A", None), row("B", "Z", group=True)], "unknown parent"),
    ],
)
def test_validate_backbone_errors(rows, message) -> None:
    with pytest.raises(PhylogenyBuildError, match=message):
        validate_backbone(rows)


# --------------------------------------------------------------------------- #
# The real curated backbone
# --------------------------------------------------------------------------- #


def test_real_backbone_is_valid_and_anchors_exist() -> None:
    backbone = load_backbone(ROOT / "data" / "curated" / "reptile_backbone.csv")
    with (ROOT / "species_crossref.csv").open(newline="", encoding="utf-8-sig") as handle:
        families = {r["family"] for r in csv.DictReader(handle)}
    for r in backbone:
        assert set(r.anchor_families) <= families, r.name
        assert r.citation, f"{r.name} has no citation"


def test_real_backbone_relationships() -> None:
    backbone = {r.name: r for r in load_backbone(ROOT / "data" / "curated" / "reptile_backbone.csv")}
    assert backbone["Aves"].parent == "Saurischia"  # birds are dinosaurs
    assert backbone["Pterosauria"].parent == backbone["Dinosauria"].parent == "Avemetatarsalia"
    assert backbone["Crocodylia"].parent == "Archosauria"
    assert backbone["Testudines"].parent == "Archelosauria"  # not grouped with Anapsida
    assert backbone["Testudines"].anapsid_skull and backbone["Mesosauria"].anapsid_skull
    assert backbone["Mesosauria"].placement_uncertain
    assert not backbone["Aves"].extinct
    assert all(backbone[n].extinct for n in ("Mesosauria", "Pterosauria", "Ornithischia"))


# --------------------------------------------------------------------------- #
# API tree builder
# --------------------------------------------------------------------------- #


def fake_node(node_id, label, species=None, family=None, group=False, age=None):
    return SimpleNamespace(
        id=node_id, label=label, species_id=species.id if species else None, species=species,
        family_taxon=family, collapsed_group=group, external_id=None, source=None,
        placement_status="confirmed" if species else None, extinct=False,
        placement_uncertain=False, anapsid_skull=False, note=None, citation=None,
        age_ma=age, age_ci_low=None, age_ci_high=None, age_source=None, age_citation=None,
        age_study_count=None, age_adjusted=False, age_unadjusted_ma=None,
        first_appearance_ma=None, last_appearance_ma=None,
    )


def test_build_phylogeny_tree_nests_and_labels_kinds() -> None:
    clade = SimpleNamespace(scientific_name="Anguimorpha", parent=None)
    family = SimpleNamespace(scientific_name="Varanidae", parent=clade)
    species = SimpleNamespace(id=7, scientific_name="Varanus varius", common_name="Lace monitor")
    nodes = [
        fake_node(1, "Root", age=250.0),
        fake_node(2, "Varanidae", species=species, family=family, age=0.0),
        fake_node(3, "Aves", group=True, age=0.0),
    ]
    edges = [SimpleNamespace(id=2, parent_node_id=1, child_node_id=3),
             SimpleNamespace(id=1, parent_node_id=1, child_node_id=2)]
    root = build_phylogeny_tree(nodes, edges)
    assert root.kind == "clade"
    assert [c.name for c in root.children] == ["Varanidae", "Aves"]  # edge-id order
    tip = root.children[0]
    assert tip.kind == "family" and tip.clade_group == "Anguimorpha"
    assert tip.representative_species.common_name == "Lace monitor"
    assert root.children[1].kind == "group"
    assert tip.stem_age_ma == 250.0  # when the lineage split off = parent's age
    assert root.stem_age_ma is None


# --------------------------------------------------------------------------- #
# Curated clade names
# --------------------------------------------------------------------------- #


def test_clade_name_labels_the_unnamed_common_ancestor() -> None:
    records = build()
    apply_clade_names(records, [CladeName("Toxicofera", "Varanidae", "Pythonidae", "Vidal & Hedges 2005")])
    named = next(r for r in records if r.label == "Toxicofera")
    assert named.key == "mrcaott4ott5" and named.citation == "Vidal & Hedges 2005"


@pytest.mark.parametrize(
    ("clades", "message"),
    [
        ([CladeName("Wrong", "Lacertidae", "Gekkonidae", "c")], "already named Squamata"),
        ([CladeName("A", "Varanidae", "Pythonidae", "c"), CladeName("B", "Pythonidae", "Varanidae", "c")],
         "name the same node"),
        ([CladeName("X", "Varanidae", "Nopeidae", "c")], "not in the tree"),
        ([CladeName("Y", "Chelidae", "Crocodylidae", "c")], "not an Open Tree clade"),
    ],
)
def test_clade_names_never_overwrite_or_collide(clades, message) -> None:
    with pytest.raises(PhylogenyBuildError, match=message):
        apply_clade_names(build(), clades)


def test_real_clade_names_file_is_valid() -> None:
    names = load_clade_names(ROOT / "data" / "curated" / "clade_names.csv")
    with (ROOT / "species_crossref.csv").open(newline="", encoding="utf-8-sig") as handle:
        families = {r["family"] for r in csv.DictReader(handle)}
    assert len(names) == len({n.name for n in names}) >= 10
    for name in names:
        assert {name.family_a, name.family_b} <= families, name.name
        assert name.citation
