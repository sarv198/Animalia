"""Species media: Wikipedia infobox status, licence rules, GBIF parsing, cache."""

from __future__ import annotations

import json

import pytest

from etl.extract import media
from etl.load.media_to_postgres import iucn_source_text

SPECIESBOX = """{{Speciesbox
| status = EN
| status_system = IUCN3.1
| status_ref = <ref name="IUCN">{{cite iucn |author=Jessop, T. |year=2019 |title=Varanus komodoensis}}</ref>
| genus = Varanus
}}"""


def test_parse_infobox_status_reads_iucn_category_and_year() -> None:
    assert media.parse_infobox_status(SPECIESBOX) == {"category": "EN", "system": "IUCN3.1", "year": 2019}


@pytest.mark.parametrize(
    "wikitext",
    [
        SPECIESBOX.replace("IUCN3.1", "NatureServe"),  # not an IUCN category
        SPECIESBOX.replace("status = EN", "status = NE"),  # 'not evaluated' is not a category
        "{{Speciesbox | genus = Varanus }}",  # no status at all
    ],
)
def test_parse_infobox_status_rejects_non_iucn(wikitext) -> None:
    assert media.parse_infobox_status(wikitext) is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://creativecommons.org/licenses/by-nc/4.0/", ("CC BY-NC 4.0", "CC BY-NC")),
        ("http://creativecommons.org/licenses/by/4.0/legalcode", ("CC BY 4.0", "CC BY")),
        ("http://creativecommons.org/publicdomain/zero/1.0/", ("CC0 1.0", "CC0")),
        ("http://creativecommons.org/licenses/by-nc-nd/4.0/", ("CC BY-NC-ND 4.0", "CC BY-NC-ND")),
        ("all rights reserved", (None, None)),
    ],
)
def test_licence_from_url(url, expected) -> None:
    assert media.licence_from_url(url) == expected


@pytest.mark.parametrize(
    ("name", "family", "allowed"),
    [
        ("CC BY-SA 4.0", "CC BY-SA", True),
        ("CC-BY-SA-3.0", "CC BY-SA", True),
        ("Public domain", "Public domain", True),
        ("CC0", "CC0", True),
        ("CC BY-ND 2.0", "CC BY-ND", False),
        ("Fair use", None, False),
    ],
)
def test_licence_family_and_policy(name, family, allowed) -> None:
    assert media.licence_family(name) == family
    assert (media.licence_family(name) in media.ALLOWED_LICENCES) is allowed


def occurrence(key, url, licence="http://creativecommons.org/licenses/by/4.0/", kind="StillImage"):
    return {"key": key, "media": [{"type": kind, "identifier": url, "license": licence,
                                   "creator": f"author{key}", "references": f"https://ex.org/{key}"}]}


def test_parse_gbif_images_filters_and_sizes() -> None:
    inat = "https://inaturalist-open-data.s3.amazonaws.com/photos/1/original.jpg"
    results = [
        occurrence(1, inat),
        occurrence(2, "http://insecure.example/x.jpg"),  # not https
        occurrence(3, "https://ex.org/nd.jpg", licence="http://creativecommons.org/licenses/by-nd/4.0/"),
        occurrence(4, "https://ex.org/sound.mp3", kind="Sound"),
        occurrence(5, "https://ex.org/ok.jpg", licence="http://creativecommons.org/licenses/by-nc/4.0/"),
        occurrence(6, "https://ex.org/ok2.jpg"),
        occurrence(7, "https://ex.org/ok3.jpg"),
    ]
    images = media.parse_gbif_images(results, limit=3)
    assert [i["page_url"] for i in images] == ["https://ex.org/1", "https://ex.org/5", "https://ex.org/6"]
    assert images[0]["image_url"].endswith("/large.jpg") and images[0]["thumbnail_url"].endswith("/medium.jpg")
    assert images[0]["licence"] == "CC BY 4.0" and images[0]["creator"] == "author1"


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise media.requests.HTTPError(str(self.status_code))


def test_get_backs_off_on_rate_limit(monkeypatch) -> None:
    replies = [FakeResponse(429, headers={"Retry-After": "0"}), FakeResponse(200, {"ok": True})]
    monkeypatch.setattr(media.requests, "get", lambda *a, **k: replies.pop(0))
    monkeypatch.setattr(media.time, "sleep", lambda s: None)
    assert media._get("https://x", {}).json() == {"ok": True}


def test_commons_image_skips_non_free(monkeypatch) -> None:
    def reply(licence):
        return FakeResponse(200, {"query": {"pages": [{"imageinfo": [{
            "url": "https://upload/x.jpg", "thumburl": "https://upload/t.jpg",
            "descriptionurl": "https://commons/x",
            "extmetadata": {"LicenseShortName": {"value": licence}, "Artist": {"value": "<a href='u'>Ann</a>"}},
        }]}]}})
    monkeypatch.setattr(media, "_get", lambda *a, **k: reply("CC BY-SA 4.0"))
    image = media.fetch_commons_image("x.jpg")
    assert image["creator"] == "Ann" and image["licence"] == "CC BY-SA 4.0"
    monkeypatch.setattr(media, "_get", lambda *a, **k: reply("CC BY-ND 4.0"))
    assert media.fetch_commons_image("x.jpg") is None
    monkeypatch.setattr(media, "_get", lambda *a, **k: FakeResponse(200, {"query": {"pages": [{"missing": True}]}}))
    assert media.fetch_commons_image("local_nonfree.jpg") is None


def test_extract_uses_cache_and_saves_each_species(tmp_path, monkeypatch) -> None:
    (tmp_path / media.CACHE_FILE).write_text(json.dumps({"A a": {"images": [], "cached": True}}))
    calls = []

    def fake_fetch(name, gbif):
        calls.append((name, gbif))
        if name == "C c":
            raise RuntimeError("network down")
        return {"retrieved": "2026-10-06", "wikipedia": None, "iucn": None, "images": []}

    monkeypatch.setattr(media, "fetch_species_media", fake_fetch)
    rows = [{"species": "A a", "gbif_usage_key": "1"}, {"species": "B b", "gbif_usage_key": "2.0"},
            {"species": "C c", "gbif_usage_key": ""}]
    with pytest.raises(RuntimeError):
        media.extract(rows, raw_dir=tmp_path)
    assert calls == [("B b", 2), ("C c", None)]  # A a came from the cache
    saved = json.loads((tmp_path / media.CACHE_FILE).read_text())
    assert set(saved) == {"A a", "B b"}  # B b kept even though C c failed
    assert set(media.cached(rows, raw_dir=tmp_path)) == {"A a", "B b"}


def test_iucn_source_text() -> None:
    entry = {"retrieved": "2026-10-06", "wikipedia": {"title": "Komodo dragon", "url": "u"},
             "iucn": {"category": "EN", "system": "IUCN3.1", "year": 2019}}
    assert iucn_source_text(entry) == 'Wikipedia, "Komodo dragon" infobox (IUCN3.1), retrieved 2026-10-06'
    assert iucn_source_text({"iucn": None, "wikipedia": None}) is None


def test_gbif_uses_only_the_photos_own_licence() -> None:
    # The occurrence record is CC BY but the photo itself carries no licence: skip it.
    occ = {"key": 9, "license": "http://creativecommons.org/licenses/by/4.0/",
           "media": [{"type": "StillImage", "identifier": "https://ex.org/a.jpg", "creator": "Ann"}]}
    assert media.parse_gbif_images([occ]) == []


def test_images_without_a_creator_need_a_public_domain_licence() -> None:
    assert not media.usable("CC BY 4.0", None)
    assert media.usable("CC BY 4.0", "Ann")
    assert media.usable("CC0 1.0", None)
    assert media.usable("Public domain", None)
    assert not media.usable("CC BY-ND 4.0", "Ann")


def test_non_commercial_photos_can_be_switched_off(monkeypatch) -> None:
    assert media.usable("CC BY-NC 4.0", "Ann")  # allowed for this non-commercial site
    monkeypatch.setattr(media, "ALLOWED_LICENCES", media.ALLOWED_LICENCES - {"CC BY-NC", "CC BY-NC-SA"})
    assert not media.usable("CC BY-NC 4.0", "Ann")
