"""Wikipedia summaries and GARD family ranges (no network, no database)."""

from __future__ import annotations

import numpy as np
import pytest
import shapely
from shapely.geometry import box

from etl.extract import summaries
from etl.transform import ranges


# --------------------------------------------------------------------------- #
# Summaries
# --------------------------------------------------------------------------- #


def _payload(**overrides):
    payload = {
        "type": "standard",
        "title": "Monitor lizard",
        "extract": (
            "Monitor lizards are lizards in the genus Varanus, the only living genus of the family Varanidae. "
            "They are native to Africa, Asia, and Oceania. Some species reach 3 m. A fourth sentence here."
        ),
        "revision": 123,
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Monitor_lizard"}},
    }
    payload.update(overrides)
    return payload


def test_summary_kept_when_it_names_the_group():
    summary = summaries.parse_summary("Varanidae", _payload())
    assert summary["title"] == "Monitor lizard"
    assert summary["url"].endswith("Monitor_lizard")
    assert summary["licence"] == "CC BY-SA 4.0"
    assert summary["revision"] == "123"
    assert "fourth sentence" not in summary["extract"]  # trimmed to three sentences


def test_summary_rejected_when_redirect_lands_elsewhere():
    assert summaries.parse_summary("Dibamidae", _payload(description="Article about something else")) is None


def test_summary_kept_for_a_redirect_to_a_taxon_article():
    payload = _payload(title="Chinese crocodile lizard", description="Species of reptile",
                       extract="The Chinese crocodile lizard is a semiaquatic anguimorph lizard.")
    assert summaries.parse_summary("Shinisauridae", payload)["title"] == "Chinese crocodile lizard"


def test_summary_kept_for_a_class_article_that_does_not_name_the_taxon():
    payload = _payload(title="Reptile", description="Class of animals", extract="Reptiles are tetrapods.")
    assert summaries.parse_summary("Reptilia", payload)["title"] == "Reptile"


def test_summary_rejected_for_a_redirect_to_a_non_taxon_article():
    payload = _payload(title="Some band", description="American rock band", extract="Some band is a band.")
    assert summaries.parse_summary("Dibamidae", payload) is None


def test_summary_rejected_for_disambiguation_pages():
    assert summaries.parse_summary("Varanidae", _payload(type="disambiguation")) is None


def test_undash_replaces_em_and_en_dashes():
    assert summaries.undash("from 1.6–67 cm long") == "from 1.6 to 67 cm long"
    assert summaries.undash("geckos — small lizards — are") == "geckos, small lizards, are"
    assert "—" not in summaries.undash("a—b") and "–" not in summaries.undash("a – b")


def test_trim_keeps_initials_and_abbreviations_inside_sentences():
    text = "Named by N. Vidal and S. B. Hedges in 2005. It has c. 4,600 species. Third. Fourth."
    assert summaries.trim(text, max_sentences=2) == "Named by N. Vidal and S. B. Hedges in 2005. It has c. 4,600 species."


def test_trim_respects_the_character_cap_but_keeps_one_sentence():
    long = "A" * 600 + ". Second sentence."
    assert summaries.trim(long, max_chars=100) == "A" * 600 + "."


# --------------------------------------------------------------------------- #
# Ranges
# --------------------------------------------------------------------------- #


def test_normalise_matches_gard_and_checklist_spellings():
    assert ranges.normalise("Varanus_komodoensis") == ranges.normalise(" varanus  komodoensis ")


def test_assign_families_uses_the_checklist_family():
    names = ["Varanus komodoensis", "Varanus niloticus", "Lanthanotus borneensis", "Unknownus newus"]
    species_family = {"varanus komodoensis": "Varanidae", "varanus niloticus": "Varanidae", "lanthanotus borneensis": "Lanthanotidae"}
    assert ranges.assign_families(names, species_family) == {"Varanidae": [0, 1], "Lanthanotidae": [2]}


def test_union_merges_overlapping_ranges_and_drops_slivers():
    merged = ranges.union([box(0, 0, 2, 2), box(1, 1, 3, 3), None])
    assert merged.geom_type == "Polygon"
    assert merged.area == pytest.approx(7, rel=0.01)


def test_to_geojson_is_rounded_and_none_when_empty():
    geojson = ranges.to_geojson(box(0.123456, 0, 10.98765, 5))
    assert geojson["type"] == "Polygon"
    for x, y in geojson["coordinates"][0]:
        assert round(x, 2) == x and round(y, 2) == y
    assert ranges.to_geojson(shapely.Polygon()) is None


def test_to_geojson_outer_rings_run_clockwise_for_d3():
    ring = shapely.geometry.shape(ranges.to_geojson(box(0, 0, 10, 5))).exterior
    assert not ring.is_ccw


@pytest.fixture
def shapefile(tmp_path):
    pyogrio = pytest.importorskip("pyogrio")
    path = tmp_path / "gard.shp"
    geoms = [box(100, -10, 120, 0), box(115, -5, 130, 5), box(110, 0, 112, 2), box(-10, 30, 0, 40)]
    pyogrio.raw.write(
        path,
        geometry=np.array(shapely.to_wkb(geoms), dtype=object),
        field_data=[np.array(["Varanus komodoensis", "Varanus salvator", "Lanthanotus borneensis", "Chamaeleo chamaeleon"], dtype=object)],
        fields=["binomial"],
        geometry_type="Polygon",
        crs="EPSG:4326",
        driver="ESRI Shapefile",
    )
    return path


def test_build_family_and_representative_ranges(shapefile):
    species_family = {
        "varanus komodoensis": "Varanidae",
        "varanus salvator": "Varanidae",
        "lanthanotus borneensis": "Lanthanotidae",
    }
    reps = {"Varanidae": "Varanus komodoensis", "Lanthanotidae": "Lanthanotus borneensis", "Cheloniidae": "Chelonia mydas"}
    out = ranges.build(["Varanidae", "Lanthanotidae", "Cheloniidae"], species_family, reps, shapefile)

    varanidae = out["Varanidae"]
    assert varanidae.species_mapped == 2
    family_area = shapely.geometry.shape(varanidae.range_geojson).area
    rep_area = shapely.geometry.shape(varanidae.rep_range_geojson).area
    assert family_area > rep_area  # the family covers more than the Komodo dragon alone

    assert out["Lanthanotidae"].species_mapped == 1
    # A marine family with no GARD polygons gets no map at either level.
    sea_turtles = out["Cheloniidae"]
    assert sea_turtles.species_mapped == 0
    assert sea_turtles.range_geojson is None and sea_turtles.rep_range_geojson is None


def test_run_skips_when_the_shapefile_is_missing(tmp_path):
    assert ranges.run(["Varanidae"], {}, {}, gard_dir=tmp_path / "none", out_dir=tmp_path) is None


# --------------------------------------------------------------------------- #
# Range text
# --------------------------------------------------------------------------- #


def test_range_prefers_a_distribution_section_and_keeps_only_place_sentences():
    text = (
        "Lead about colour.\n== Description ==\nSmall.\n== Distribution and habitat ==\n"
        "Very few studies exist. They live in Africa and Madagascar. A few reach southern Europe. A third."
    )
    assert summaries.range_from_article(text) == "They live in Africa and Madagascar. A few reach southern Europe."


def test_range_skips_fossil_sentences():
    assert summaries.range_from_article("Fossils are found in Europe. They are native to Mexico.") == "They are native to Mexico."


def test_undash_keeps_joined_words_hyphenated():
    assert summaries.undash("snout–vent length") == "snout-vent length"


def test_range_ignores_fossil_sections_and_falls_back_to_a_place_sentence():
    text = "They are lizards native to Southeast Asia.\n== Fossil distribution ==\nFossils occur in Europe."
    assert summaries.range_from_article(text) == "They are lizards native to Southeast Asia."


def test_range_needs_a_place_not_just_a_habitat():
    text = "Agamids inhabit warm environments, ranging from deserts to rainforests."
    assert summaries.range_from_article(text) is None


def test_fetch_range_falls_back_to_the_representative_species(monkeypatch):
    articles = {"Varanidae": "A family of lizards.", "Komodo dragon": "== Distribution ==\nIt lives on islands in Indonesia."}
    monkeypatch.setattr(summaries, "fetch_article_text", lambda title: articles[title])
    monkeypatch.setattr(summaries.time, "sleep", lambda s: None)
    summary = {"title": "Varanidae", "url": "u", "extract": "A family of lizards."}
    where = summaries.fetch_range(summary, ("Komodo dragon", "https://en.wikipedia.org/wiki/Komodo_dragon"))
    assert where == {
        "text": "It lives on islands in Indonesia.", "scope": "species",
        "title": "Komodo dragon", "url": "https://en.wikipedia.org/wiki/Komodo_dragon",
    }
