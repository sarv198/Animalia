"""Species images (Wikimedia Commons, GBIF) and IUCN status from Wikipedia.

For each representative species:

  Wikipedia  the English article (found by scientific name, following
             redirects) gives the page link, the lead image, and the IUCN Red
             List category as stated in the article's infobox
             (`status = EN`, `status_system = IUCN3.1`). That is Wikipedia's
             statement of the IUCN category, not the IUCN's own record.
  Commons    licence and author of the lead image. Images that are not on
             Commons (local, non-free files) are skipped.
  GBIF       a few occurrence photos of the species (mostly iNaturalist).

Only openly licensed images are kept (ALLOWED_LICENCES); each keeps its
licence, creator and source page so it can be credited. Images are linked, not
copied. Results are cached in data/raw/media/species_media.json; only species
not yet cached are fetched unless refresh is requested.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

from etl.config import ALLOW_NONCOMMERCIAL_IMAGES, MEDIA_RAW_DIR, WIKIMEDIA_CONTACT

logger = logging.getLogger(__name__)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
GBIF_OCCURRENCE_SEARCH = "https://api.gbif.org/v1/occurrence/search"
# Wikimedia's User-Agent policy: name the tool and give a contact.
HEADERS = {"User-Agent": f"AnimaliaReptilePhylogeny/0.1 ({WIKIMEDIA_CONTACT}) python-requests"}
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_CALLS = 1.0
MAX_RETRIES = 6
CACHE_FILE = "species_media.json"

GBIF_IMAGES_PER_SPECIES = 3
IUCN_CATEGORIES = frozenset({"LC", "NT", "VU", "EN", "CR", "EW", "EX", "DD"})
# Licences that allow showing a photo on a public site, with credit. The
# non-commercial (NC) ones are allowed only while the site is non-commercial
# (ALLOW_NONCOMMERCIAL_IMAGES). No-derivatives (ND) is never used.
NO_CREDIT_NEEDED = frozenset({"CC0", "Public domain"})
ALLOWED_LICENCES = frozenset(
    {"CC0", "Public domain", "CC BY", "CC BY-SA"}
    | ({"CC BY-NC", "CC BY-NC-SA"} if ALLOW_NONCOMMERCIAL_IMAGES else set())
)


def usable(licence: str | None, creator: str | None) -> bool:
    """An image is usable if its licence is allowed and, unless it is public
    domain / CC0, it names a creator to credit (CC licences require that)."""
    family = licence_family(licence)
    return family in ALLOWED_LICENCES and (family in NO_CREDIT_NEEDED or bool(creator))


# --------------------------------------------------------------------------- #
# Licences
# --------------------------------------------------------------------------- #


def licence_from_url(url: str | None) -> tuple[str | None, str | None]:
    """'http://creativecommons.org/licenses/by-nc/4.0/' -> ('CC BY-NC 4.0', family 'CC BY-NC')."""
    if not url:
        return None, None
    text = url.lower()
    if "publicdomain/zero" in text:
        return "CC0 1.0", "CC0"
    if "publicdomain/mark" in text:
        return "Public domain", "Public domain"
    match = re.search(r"licenses/([a-z-]+)/(\d\.\d)", text)
    if not match:
        return None, None
    family = "CC " + match.group(1).upper()
    return f"{family} {match.group(2)}", family


def licence_family(short_name: str | None) -> str | None:
    """'CC BY-SA 4.0' -> 'CC BY-SA'; 'Public domain' -> 'Public domain'."""
    if not short_name:
        return None
    text = short_name.strip()
    if text.lower().startswith("public domain") or text.upper() == "PD":
        return "Public domain"
    if text.upper().startswith("CC0"):
        return "CC0"
    match = re.match(r"(CC[ -]BY(?:-(?:NC|SA|ND))*(?:-(?:SA|ND))?)", text.upper())
    return match.group(1).replace("CC-", "CC ") if match else None


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    plain = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", plain).strip() or None


def _get(url: str, params: dict[str, Any], headers: dict[str, str] | None = None) -> requests.Response:
    """GET that backs off on 429/503, honouring Retry-After (Wikimedia rate limits)."""
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code not in (429, 503):
            resp.raise_for_status()
            return resp
        retry_after = resp.headers.get("Retry-After", "")
        wait = int(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1)
        logger.info("rate limited by %s; waiting %ss", url, wait)
        time.sleep(min(wait, 120))
    resp.raise_for_status()
    return resp


# --------------------------------------------------------------------------- #
# Wikipedia
# --------------------------------------------------------------------------- #

_STATUS_RE = re.compile(r"\|\s*status\s*=\s*([A-Za-z]{2})\b")
_SYSTEM_RE = re.compile(r"\|\s*status_system\s*=\s*([A-Za-z0-9.]+)")
_IUCN_CITE_YEAR_RE = re.compile(
    r"\{\{\s*cite iucn[^{}]*?\|\s*(?:year|date)\s*=\s*[^|{}]*?(\d{4})", re.IGNORECASE
)


def parse_infobox_status(wikitext: str) -> dict[str, Any] | None:
    """IUCN category from a Wikipedia taxobox/speciesbox, if it states one.

    Only categories under an IUCN status system count (Wikipedia also uses
    NatureServe and others in the same field)."""
    status = _STATUS_RE.search(wikitext)
    system = _SYSTEM_RE.search(wikitext)
    if not status or not system or not system.group(1).upper().startswith("IUCN"):
        return None
    category = status.group(1).upper()
    if category not in IUCN_CATEGORIES:
        return None
    year = _IUCN_CITE_YEAR_RE.search(wikitext)
    return {
        "category": category,
        "system": system.group(1),
        "year": int(year.group(1)) if year else None,
    }


def fetch_wikipedia(scientific_name: str) -> dict[str, Any] | None:
    """Article title/url, lead image file name and infobox status, or None."""
    resp = _get(
        WIKIPEDIA_API,
        params={
            "action": "query", "titles": scientific_name, "redirects": 1,
            "prop": "pageimages|revisions|info", "piprop": "name",
            "rvprop": "content", "rvslots": "main", "inprop": "url",
            "format": "json", "formatversion": 2,
        },
        headers=HEADERS,
    )
    pages = resp.json().get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    page = pages[0]
    wikitext = (page.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("content", "")
    return {
        "title": page.get("title"),
        "url": page.get("fullurl"),
        "image_file": page.get("pageimage"),
        "iucn": parse_infobox_status(wikitext),
    }


def fetch_commons_image(file_name: str) -> dict[str, Any] | None:
    """Image URLs + licence + author for a Commons file; None if not on Commons
    (e.g. a local non-free file) or not openly licensed."""
    resp = _get(
        COMMONS_API,
        params={
            "action": "query", "titles": f"File:{file_name}", "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": 960,
            "format": "json", "formatversion": 2,
        },
        headers=HEADERS,
    )
    pages = resp.json().get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing") or not pages[0].get("imageinfo"):
        return None
    info = pages[0]["imageinfo"][0]
    meta = info.get("extmetadata", {})
    licence = _strip_html(meta.get("LicenseShortName", {}).get("value"))
    creator = _strip_html(meta.get("Artist", {}).get("value")) or _strip_html(meta.get("Credit", {}).get("value"))
    if not usable(licence, creator):
        return None
    return {
        "source": "Wikimedia Commons",
        "image_url": info.get("thumburl") or info.get("url"),
        "thumbnail_url": info.get("thumburl") or info.get("url"),
        "page_url": info.get("descriptionurl"),
        "licence": licence,
        "licence_url": meta.get("LicenseUrl", {}).get("value"),
        "creator": creator,
    }


# --------------------------------------------------------------------------- #
# GBIF
# --------------------------------------------------------------------------- #


def _sized(url: str, size: str) -> str:
    """iNaturalist open-data photos come in sizes; 'original' can be huge."""
    if "inaturalist-open-data" in url and "/original." in url:
        return url.replace("/original.", f"/{size}.")
    return url


def parse_gbif_images(results: list[dict[str, Any]], limit: int = GBIF_IMAGES_PER_SPECIES) -> list[dict[str, Any]]:
    """Up to ``limit`` openly licensed still images, one per occurrence."""
    images: list[dict[str, Any]] = []
    for occurrence in results:
        for media in occurrence.get("media", []):
            url = media.get("identifier")
            if media.get("type") != "StillImage" or not url or not url.startswith("https://"):
                continue
            # The photo's own licence only: the occurrence record's licence
            # covers the record, not necessarily the image.
            licence, _ = licence_from_url(media.get("license"))
            creator = media.get("creator") or media.get("rightsHolder")
            if not usable(licence, creator):
                continue
            images.append({
                "source": "GBIF",
                "image_url": _sized(url, "large"),
                "thumbnail_url": _sized(url, "medium"),
                "page_url": media.get("references") or f"https://www.gbif.org/occurrence/{occurrence.get('key')}",
                "licence": licence,
                "licence_url": media.get("license"),
                "creator": creator,
            })
            break  # one image per occurrence: more variety
        if len(images) >= limit:
            break
    return images


def fetch_gbif_images(gbif_taxon_id: int) -> list[dict[str, Any]]:
    resp = _get(
        GBIF_OCCURRENCE_SEARCH,
        params={"taxonKey": gbif_taxon_id, "mediaType": "StillImage", "limit": 30},
    )
    return parse_gbif_images(resp.json().get("results", []))


# --------------------------------------------------------------------------- #
# Orchestration + cache
# --------------------------------------------------------------------------- #


def fetch_species_media(scientific_name: str, gbif_taxon_id: int | None) -> dict[str, Any]:
    wiki = fetch_wikipedia(scientific_name)
    time.sleep(SLEEP_BETWEEN_CALLS)
    images: list[dict[str, Any]] = []
    if wiki and wiki.get("image_file"):
        commons = fetch_commons_image(wiki["image_file"])
        time.sleep(SLEEP_BETWEEN_CALLS)
        if commons:
            images.append(commons)
    if gbif_taxon_id:
        images.extend(fetch_gbif_images(gbif_taxon_id))
        time.sleep(SLEEP_BETWEEN_CALLS)
    return {
        "retrieved": date.today().isoformat(),
        "wikipedia": {"title": wiki["title"], "url": wiki["url"]} if wiki else None,
        "iucn": wiki.get("iucn") if wiki else None,
        "images": images,
    }


def cached(rows: list[dict[str, str]], raw_dir: Path = MEDIA_RAW_DIR) -> dict[str, dict[str, Any]]:
    """Whatever is already cached for ``rows`` (no network)."""
    path = raw_dir / CACHE_FILE
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    wanted = {row["species"].strip() for row in rows}
    return {name: entry for name, entry in cache.items() if name in wanted}


def extract(
    rows: list[dict[str, str]], raw_dir: Path = MEDIA_RAW_DIR, refresh: bool = False
) -> dict[str, dict[str, Any]]:
    """Media for every species in ``rows`` (crossref rows), keyed by scientific
    name. Cached species are reused unless ``refresh``."""
    path = raw_dir / CACHE_FILE
    cache: dict[str, dict[str, Any]] = {}
    if path.exists() and not refresh:
        cache = json.loads(path.read_text(encoding="utf-8"))
    raw_dir.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        path.write_text(json.dumps(cache, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")

    fetched = 0
    for row in rows:
        name = row["species"].strip()
        if name in cache:
            continue
        gbif = row.get("gbif_usage_key") or ""
        cache[name] = fetch_species_media(name, int(float(gbif)) if gbif.strip() else None)
        fetched += 1
        save()  # after every species, so an interruption loses nothing
    save()
    logger.info("media: %d species fetched, %d cached", fetched, len(cache) - fetched)
    wanted = {row["species"].strip() for row in rows}
    return {name: entry for name, entry in cache.items() if name in wanted}
