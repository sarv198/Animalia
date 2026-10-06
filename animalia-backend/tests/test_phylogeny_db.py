"""Integration tests against the loaded phylogeny in Postgres.

Skipped unless the database is reachable and `python etl/run_pipeline.py` has
been run. These check the real tree's biology through the API.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.database import SessionLocal
from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def _phylogeny_loaded() -> bool:
    db = SessionLocal()
    try:
        return bool(db.execute(text("SELECT count(*) FROM phylo_nodes")).scalar())
    except (OperationalError, ProgrammingError):
        return False
    finally:
        db.close()


pytestmark = pytest.mark.skipif(
    not _phylogeny_loaded(), reason="phylogeny not loaded; run etl/run_pipeline.py"
)

client = TestClient(app)


@pytest.fixture(scope="module")
def tree() -> dict:
    response = client.get("/api/phylogeny/reptiles")
    assert response.status_code == 200
    return response.json()


def _walk(node, path=()):
    path = path + (node["id"],)
    yield node, path
    for child in node["children"]:
        yield from _walk(child, path)


def _paths(tree) -> dict[str, tuple[int, ...]]:
    return {node["name"]: path for node, path in _walk(tree) if node["kind"] != "clade"}


def _closeness(paths, a, b) -> int:
    """Number of shared ancestors; larger = more closely related."""
    return sum(1 for x, y in zip(paths[a], paths[b]) if x == y)


def test_root_and_tip_counts(tree) -> None:
    assert tree["name"] == "Reptilia"
    nodes = [n for n, _ in _walk(tree)]
    families = [n for n in nodes if n["kind"] == "family"]
    groups = {n["name"] for n in nodes if n["kind"] == "group"}
    with (ROOT / "species_crossref.csv").open(newline="", encoding="utf-8-sig") as handle:
        assert len(families) == len(list(csv.DictReader(handle))) == 85
    assert groups == {"Mesosauria", "Pterosauria", "Ornithischia", "Sauropodomorpha", "Aves"}


def test_family_tips_are_complete(tree) -> None:
    for node, _ in _walk(tree):
        if node["kind"] != "family":
            continue
        assert node["representative_species"], node["name"]
        assert node["clade_group"], node["name"]
        assert node["placement_status"] in {"confirmed", "flagged", "unknown"}
        assert node["children"] == []


def test_varanidae_is_closer_to_snakes_than_to_geckos(tree) -> None:
    paths = _paths(tree)
    assert _closeness(paths, "Varanidae", "Pythonidae") > _closeness(paths, "Varanidae", "Gekkonidae")
    # Toxicofera: anguimorphs sit with iguanians, then with snakes.
    assert _closeness(paths, "Varanidae", "Iguanidae") > _closeness(paths, "Varanidae", "Pythonidae")


def test_archosaur_and_turtle_relationships(tree) -> None:
    paths = _paths(tree)
    assert _closeness(paths, "Crocodylidae", "Aves") > _closeness(paths, "Crocodylidae", "Testudinidae")
    assert _closeness(paths, "Testudinidae", "Crocodylidae") > _closeness(paths, "Testudinidae", "Lacertidae")
    assert _closeness(paths, "Pterosauria", "Aves") > _closeness(paths, "Pterosauria", "Crocodylidae")
    assert _closeness(paths, "Aves", "Sauropodomorpha") > _closeness(paths, "Aves", "Ornithischia")


def test_mesosaurs_branch_before_all_living_reptiles(tree) -> None:
    root_children = {c["name"] for c in tree["children"]}
    assert root_children == {"Mesosauria", "Sauria"}


def _node(tree, name) -> dict:
    return next(n for n, _ in _walk(tree) if n["name"] == name)


def _mrca(tree, a, b) -> dict:
    """The common-ancestor node of two named tips."""
    nodes = {n["id"]: n for n, _ in _walk(tree)}
    paths = _paths(tree)
    shared = [x for x, y in zip(paths[a], paths[b]) if x == y]
    return nodes[shared[-1]]


def test_every_node_is_dated_and_ancestors_are_older(tree) -> None:
    for node, _ in _walk(tree):
        assert node["age_ma"] is not None and node["age_source"], node["name"]
        for child in node["children"]:
            oldest = max(child["age_ma"], child["first_appearance_ma"] or 0)
            assert oldest <= node["age_ma"] + 1e-6, (node["name"], child["name"])
            assert child["stem_age_ma"] == node["age_ma"]


def test_living_tips_are_present_day_and_extinct_tips_end_at_last_fossil(tree) -> None:
    for node, _ in _walk(tree):
        if node["children"]:
            continue
        if node["extinct"]:
            assert node["age_ma"] == node["last_appearance_ma"] and node["first_appearance_ma"]
        else:
            assert node["age_ma"] == 0 and node["age_source"] == "present"


def test_most_splits_are_dated_by_timetree(tree) -> None:
    """Guards against TimeTree silently failing and everything being interpolated."""
    living_splits = [
        n for n, _ in _walk(tree)
        if n["kind"] == "clade" and n["source"] == "Open Tree of Life"
    ]
    from_timetree = [n for n in living_splits if n["age_source"] == "TimeTree 5"]
    assert len(from_timetree) >= 0.85 * len(living_splits)
    assert all(n["age_study_count"] for n in from_timetree)


def test_key_ages_match_the_literature(tree) -> None:
    # Broad windows around published molecular / fossil estimates.
    assert 260 <= _node(tree, "Sauria")["age_ma"] <= 300
    assert 240 <= _node(tree, "Archelosauria")["age_ma"] <= 275
    toxicofera = _mrca(tree, "Varanidae", "Pythonidae")
    assert 140 <= toxicofera["age_ma"] <= 200
    assert _mrca(tree, "Varanidae", "Gekkonidae")["age_ma"] > toxicofera["age_ma"]
    assert _node(tree, "Archosauria")["age_ma"] >= _node(tree, "Avemetatarsalia")["age_ma"]
    assert _node(tree, "Reptilia")["age_ma"] >= 300
    ptero = _node(tree, "Pterosauria")
    assert (ptero["first_appearance_ma"], ptero["last_appearance_ma"]) == (227.0, 66.0)
    assert 40 <= _node(tree, "Varanidae")["stem_age_ma"] <= 100


def test_age_check_catches_a_child_older_than_its_parent() -> None:
    """Corrupt one node inside a transaction that is always rolled back."""
    from app.models import PhyloNode, PhylogenyEdge
    from etl.validate.checks import ValidationError, check_phylogeny_ages

    db = SessionLocal()
    try:
        edge = db.query(PhylogenyEdge).first()
        parent = db.get(PhyloNode, edge.parent_node_id)
        child = db.get(PhyloNode, edge.child_node_id)
        child.age_ma = parent.age_ma + 50
        db.flush()
        with pytest.raises(ValidationError, match="older than its parent"):
            check_phylogeny_ages(db)
    finally:
        db.rollback()
        db.close()


def test_representative_species_profile_resolves(tree) -> None:
    varanidae = next(n for n, _ in _walk(tree) if n["name"] == "Varanidae")
    species_id = varanidae["representative_species"]["id"]
    response = client.get(f"/api/species/{species_id}")
    assert response.status_code == 200
    assert response.json()["taxonomy"]["family"] == "Varanidae"


def test_reptile_database_names_and_swapped_representatives(tree) -> None:
    families = {n["name"]: n for n, _ in _walk(tree) if n["kind"] == "family"}
    assert {"Anolidae", "Anomalepididae"} <= set(families)
    assert not {"Dactyloidae", "Anomalepidae", "Anniellidae"} & set(families)
    assert families["Phyllodactylidae"]["representative_species"]["scientific_name"] == "Tarentola mauritanica"
    assert families["Micrelapidae"]["representative_species"]["scientific_name"] == "Micrelaps bicoloratus"
    for node in families.values():  # every placement says where membership came from
        assert "The Reptile Database" in node["note"], node["name"]


def test_classification_tree_has_no_stale_families() -> None:
    clades = client.get("/api/tree/reptiles").json()
    names = {f["name"] for clade in clades for f in clade["children"]}
    assert "Anolidae" in names and "Dactyloidae" not in names and "Anniellidae" not in names
    assert len(names) == 85


def test_loader_prunes_species_that_left_the_csv() -> None:
    """Drop one row and prune inside a transaction that is always rolled back."""
    from app.models import Species, Taxon
    from etl.load.to_postgres import LoadStats, prune

    with (ROOT / "species_crossref.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    dropped = next(r for r in rows if r["family"] == "Shinisauridae")  # sole species of its family
    db = SessionLocal()
    try:
        stats = LoadStats()
        prune(db, [r for r in rows if r is not dropped], stats)
        assert stats.species_removed == 1
        assert stats.taxa_removed == 2  # its species taxon and its family
        assert db.query(Species).filter(Species.scientific_name == dropped["species"]).count() == 0
        assert db.query(Taxon).filter(Taxon.scientific_name == "Shinisauridae").count() == 0
    finally:
        db.rollback()
        db.close()


def test_only_evidence_based_conflicts_stay_flagged(tree) -> None:
    families = {n["name"]: n for n, _ in _walk(tree) if n["kind"] == "family"}
    flagged = {f for f, n in families.items() if n["placement_status"] == "flagged"}
    unknown = {f for f, n in families.items() if n["placement_status"] == "unknown"}
    assert flagged == {"Anguidae", "Crocodylidae", "Cylindrophiidae"}
    assert unknown == {"Rhineuridae"}
    for name in ("Gymnophthalmidae", "Typhlopidae"):
        assert families[name]["placement_status"] == "confirmed"
        assert "by hand" in families[name]["note"]
    assert "taxonomy alone" in families["Colubridae"]["note"]


def test_latest_representative_swaps(tree) -> None:
    families = {n["name"]: n for n, _ in _walk(tree) if n["kind"] == "family"}
    assert families["Diploglossidae"]["representative_species"]["scientific_name"] == "Diploglossus pleii"
    assert families["Micrelapidae"]["representative_species"]["common_name"] == "Kenya Two-headed Snake"


def test_curated_clade_names_sit_on_the_right_nodes(tree) -> None:
    assert _mrca(tree, "Varanidae", "Pythonidae")["name"] == "Toxicofera"
    assert _mrca(tree, "Corytophanidae", "Tropiduridae")["name"] == "Pleurodonta"
    assert _mrca(tree, "Elapidae", "Micrelapidae")["name"] == "Elapoidea"
    assert _mrca(tree, "Pelomedusidae", "Podocnemididae")["name"] == "Pelomedusoides"


def test_squamata_is_a_fossil_minimum_raised_to_molecular_dates(tree) -> None:
    squamata = _node(tree, "Squamata")
    assert squamata["age_source"] == "fossil minimum"
    assert squamata["age_adjusted"] and squamata["age_unadjusted_ma"] == 170.0
    assert squamata["age_ma"] >= _node(tree, "Bifurcata")["age_ma"]


def test_species_detail_has_credited_images_and_sourced_status() -> None:
    from app.models import Species

    db = SessionLocal()
    try:
        species = db.query(Species).all()
        with_images = [s for s in species if s.media]
        assert len(with_images) >= 0.75 * len(species)
        sample = with_images[0]
    finally:
        db.close()
    detail = client.get(f"/api/species/{sample.id}").json()
    image = detail["images"][0]
    assert image["url"].startswith("https://") and image["licence"] and (image["creator"] or image["page_url"])
    for s in species:
        if s.iucn_category:
            assert "Wikipedia" in s.iucn_source


def test_tree_payload_carries_a_credited_photo_per_family(tree) -> None:
    families = [n for n, _ in _walk(tree) if n["kind"] == "family"]
    with_photo = [n for n in families if n["representative_species"]["image"]]
    assert len(with_photo) >= 0.9 * len(families)
    for node in with_photo:
        image = node["representative_species"]["image"]
        assert image["url"].startswith("https://") and image["licence"] and image["creator"]


def test_sources_endpoint_lists_versions() -> None:
    sources = {s["name"]: s for s in client.get("/api/phylogeny/sources").json()}
    assert sources["The Reptile Database"]["version"] == "2026-06"
    assert sources["Open Tree of Life"]["version"].startswith("opentree")
    assert sources["TimeTree 5"]["version"]
