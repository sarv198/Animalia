"""Whole-family check: unit tests on a hand-built forest. No network, no database."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from etl.extract import opentree, reptiledb
from etl.transform import family_check
from etl.transform.family_check import check_families

# Three Open Tree-style subtrees (label_format=id). Internal nodes without an
# OTT id stand in for unnamed ancestors.
GROUPS = [
    # FamA = ott1-3 (one clean branch); FamB = ott4-6 plus stray ott7; FamC = ott8;
    # FamJ = ott30 (a species with two subspecies tips) + ott33.
    "(((ott1,ott2)a,ott3)b,(ott4,(ott5,ott6)c)d,(ott7,ott8)e,((ott31,ott32)ott30,ott33)f)rootA;",
    # FamF = ott9, ott10 with FamG's ott11 nested inside.
    "((ott9,ott11)g,ott10)rootB;",
    # FamH = ott12-14, each beside a larger FamI group: no branch stands for FamH.
    "((ott12,(ott20,ott21,ott22)h)i,(ott13,(ott23,ott24,ott25)j)k,(ott14,(ott26,ott27)l)m)rootC;",
]

FAMILIES = {
    "FamA": [1, 2, 3], "FamB": [4, 5, 6, 7], "FamC": [8], "FamF": [9, 10], "FamG": [11],
    "FamH": [12, 13, 14], "FamI": [20, 21, 22, 23, 24, 25, 26, 27], "FamJ": [30, 33],
}


def checklist_and_matches(extra=()):
    rows, matches = [], {}
    for fam, otts in FAMILIES.items():
        for ott in otts:
            rows.append({"species": f"Sp {ott}", "family": fam})
            matches[f"Sp {ott}"] = {"ott_id": ott, "synonym": False}
    rows.append({"species": "Sp nowhere", "family": "FamD"})  # in checklist, not in the tree
    rows.extend(extra)
    return pd.DataFrame(rows), matches


def run_check(reps, extra=(), extra_matches=None):
    sheet, matches = checklist_and_matches(extra)
    matches.update(extra_matches or {})
    return check_families(GROUPS, sheet, matches, reps, checklist_label="Test DB")


def test_clean_family_is_confirmed() -> None:
    result = run_check({"FamA": 1})["FamA"]
    assert result.status == "confirmed"
    assert result.representative_in_main_branch is True
    assert result.main_branch_species == ["Sp 1", "Sp 2", "Sp 3"]
    assert "All 3 of its species" in result.note


def test_stray_member_is_flagged_and_named() -> None:
    result = run_check({"FamB": 4})["FamB"]
    assert result.status == "flagged"
    assert (result.main_branch_members, result.main_branch_outsiders) == (3, 0)
    assert "3 of its 4 species form the main branch" in result.note
    assert "1 sits elsewhere (e.g. Sp 7)" in result.note
    assert result.representative_in_main_branch is True


def test_representative_outside_main_branch_is_reported() -> None:
    result = run_check({"FamB": 7})["FamB"]
    assert result.representative_in_main_branch is False
    assert "representative species is outside the main branch" in result.note


def test_intruding_family_is_named() -> None:
    result = run_check({"FamF": 9})["FamF"]
    assert result.status == "flagged"
    assert "with 1 species of other families inside it (FamG (1))" in result.note


def test_family_spread_among_others_has_no_main_branch() -> None:
    result = run_check({"FamH": 12})["FamH"]
    assert result.status == "flagged"
    assert result.representative_in_main_branch is None
    assert "no single branch stands for the family" in result.note
    assert "FamI (8)" in result.note


def test_species_with_subspecies_counts_as_a_member() -> None:
    result = run_check({"FamJ": 30})["FamJ"]
    assert result.status == "confirmed" and result.species_in_tree == 2
    assert result.representative_in_main_branch is True


def test_single_species_and_unknown_families() -> None:
    results = run_check({"FamC": 8, "FamD": 99, "FamZ": 1})
    assert results["FamC"].status == "confirmed"
    assert results["FamD"].status == "unknown" and "None of its 1 species" in results["FamD"].note
    assert results["FamZ"].status == "unknown" and "Not a family in Test DB" in results["FamZ"].note


def test_name_collision_is_not_counted_for_either_family() -> None:
    # A second name in another family resolving to ott1 makes ott1 ambiguous.
    results = run_check(
        {"FamA": 2},
        extra=[{"species": "Sp clash", "family": "FamC"}],
        extra_matches={"Sp clash": {"ott_id": 1, "synonym": True}},
    )
    assert results["FamA"].species_in_tree == 2  # ott1 dropped, ott2 + ott3 remain


def test_run_adds_taxonomy_only_note_and_family_ids(tmp_path, monkeypatch) -> None:
    sheet, matches = checklist_and_matches()
    xlsx = tmp_path / "reptile_checklist_2026_06.xlsx"
    sheet.assign(order="Sauria").rename(columns={"species": "Species", "family": "Family"}).to_excel(xlsx, index=False)
    monkeypatch.setattr(reptiledb, "checklist_path", lambda *a, **k: xlsx)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / opentree.GROUP_SUBTREES_FILE).write_text(json.dumps({f"G{i}": {"newick": g} for i, g in enumerate(GROUPS)}))
    (raw / opentree.CHECKLIST_MATCHES_FILE).write_text(json.dumps(matches))
    (raw / opentree.SPECIES_SUPPORT_FILE).write_text(json.dumps(
        {"1": ["ot_1@tree1"], "4": [], "5": ["ot_1@tree1"], "6": ["ot_1@tree1"], "7": ["ot_2@tree1"]}
    ))
    (raw / opentree.FAMILY_TNRS_FILE).write_text(json.dumps({"results": [
        {"name": "FamA", "matches": [{"score": 1.0, "is_synonym": False, "taxon": {"name": "FamA", "rank": "family", "ott_id": 500}}]},
    ]}))
    crossref = tmp_path / "crossref.csv"
    crossref.write_text("clade_group,family,species,ott_id\nX,FamA,Sp 1,1\nX,FamB,Sp 4,4\n")

    placement, checks, stale = family_check.run(crossref, raw_dir=raw, overrides_csv=tmp_path / "none.csv")
    assert stale == []
    assert placement["FamA"].ott_id == 500 and placement["FamA"].status == "confirmed"
    assert checks["FamA"].representative_trees == 1
    assert checks["FamB"].representative_trees == 0
    assert "taxonomy alone" in placement["FamB"].note
    assert "The Reptile Database, 2026-06 release" in placement["FamA"].note


def test_reptile_database_citation(tmp_path) -> None:
    path = tmp_path / "reptile_checklist_2026_06.xlsx"
    path.write_bytes(b"PK")
    text = reptiledb.citation(path)
    assert text.startswith("Uetz, P., Freed, P., Aguilar, R., Reyes, F., Kudera, J. & Hošek, J. (eds.) (2026)")
    assert "http://www.reptile-database.org, accessed " in text


def test_best_species_match_prefers_accepted_name() -> None:
    result = {"name": "X y", "matches": [
        {"score": 1.0, "is_synonym": True, "taxon": {"rank": "species", "ott_id": 2}},
        {"score": 1.0, "is_synonym": False, "taxon": {"rank": "species", "ott_id": 1}},
        {"score": 1.0, "is_synonym": False, "taxon": {"rank": "genus", "ott_id": 3}},
    ]}
    assert opentree.best_species_match(result) == {"ott_id": 1, "synonym": False}
    assert opentree.best_species_match({"name": "Z", "matches": []}) is None


@pytest.mark.parametrize(
    ("text", "tips"),
    [("((ott1,ott2)ott9,ott3)ott10;", ["ott1", "ott2", "ott3"]), ("ott5;", ["ott5"])],
)
def test_newick_tip_ids(text, tips) -> None:
    assert sorted(opentree.newick_tip_ids(text)) == tips


def test_taxonomy_only_strays_are_set_aside() -> None:
    # FamB's stray (ott7) is in no published tree: it no longer counts.
    support = {4: ["t"], 5: ["t"], 6: ["t"], 7: []}
    sheet, matches = checklist_and_matches()
    result = check_families(GROUPS, sheet, matches, {"FamB": 4}, checklist_label="Test DB",
                            published_trees=lambda o: support.get(o, ["t"]))["FamB"]
    assert result.status == "confirmed" and result.taxonomy_only_set_aside == 1
    assert "1 species that Open Tree places by taxonomy alone (in no published tree) was not counted" in result.note


def test_strays_in_published_trees_keep_the_flag() -> None:
    sheet, matches = checklist_and_matches()
    result = check_families(GROUPS, sheet, matches, {"FamB": 4}, checklist_label="Test DB",
                            published_trees=lambda o: ["ot_9@tree1"])["FamB"]
    assert result.status == "flagged" and result.taxonomy_only_set_aside == 0


def test_taxonomy_only_intruder_is_set_aside() -> None:
    sheet, matches = checklist_and_matches()
    result = check_families(GROUPS, sheet, matches, {"FamF": 9}, checklist_label="Test DB",
                            published_trees=lambda o: [] if o == 11 else ["t"])["FamF"]
    assert result.status == "confirmed"


def write_overrides(path, rows):
    path.write_text("family,status,reason,citation\n" + "".join(f"{r}\n" for r in rows), encoding="utf-8")


def test_overrides_apply_with_reason_and_citation(tmp_path) -> None:
    path = tmp_path / "overrides.csv"
    write_overrides(path, ["FamF,confirmed,Old trees,Smith 2020", "FamA,confirmed,Not needed,Jones 2021"])
    checks = run_check({"FamF": 9, "FamA": 1})
    stale = family_check.apply_overrides(checks, family_check.load_overrides(path))
    assert checks["FamF"].status == "confirmed" and checks["FamF"].override == "Old trees"
    assert "Status set to confirmed by hand: Old trees (Smith 2020)." in checks["FamF"].note
    assert stale == ["FamA"]  # already confirmed without the override


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (["FamF,confirmed,Old trees,"], "reason and a citation"),
        (["FamF,great,Old trees,Smith 2020"], "not a placement status"),
        (["FamF,confirmed,a,b", "FamF,confirmed,a,b"], "duplicate"),
    ],
)
def test_bad_overrides_are_rejected(tmp_path, rows, message) -> None:
    path = tmp_path / "overrides.csv"
    write_overrides(path, rows)
    with pytest.raises(ValueError, match=message):
        family_check.load_overrides(path)


def test_override_for_unknown_family_is_rejected() -> None:
    with pytest.raises(ValueError, match="not in the data"):
        family_check.apply_overrides(run_check({"FamA": 1}), {
            "FamQ": family_check.FamilyOverride("FamQ", "confirmed", "r", "c")
        })


def test_real_overrides_file_is_valid() -> None:
    overrides = family_check.load_overrides(family_check.FAMILY_OVERRIDES_PATH)
    assert set(overrides) == {"Gymnophthalmidae", "Typhlopidae"}
    assert all(o.status == "confirmed" and o.citation for o in overrides.values())
