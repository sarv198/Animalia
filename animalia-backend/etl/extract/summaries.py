"""Short descriptions of named families, clades and groups, from Wikipedia.

For each name shown in the tree (Varanidae, Toxicofera, Aves, ...) the English
Wikipedia page summary (the article lead, following redirects: Aves -> Bird)
gives a few sentences describing the group. A summary is kept only if it is an
ordinary article that names the group, or that Wikipedia describes as a taxon
(a redirect such as Shinisauridae -> Chinese crocodile lizard, the family's
only species). When the name is a disambiguation page, the reptile sense is
tried ("Acrodonta (lizard)").

Each summary also gets a sentence or two on where the group lives ("range"):
from a Distribution / Range / Biogeography section of the same article, else
the first sentence anywhere in it that both describes a distribution ("native
to", "found in", ...) and names a place, else the same from the representative
species' article (marked as the species' range). Groups whose articles say
nothing about where they live get no range text.

The text is CC BY-SA 4.0: it is shown with the article link and the licence.
It is lightly adapted, and the attribution says so: trimmed to a few sentences,
and dashes replaced (the site uses none). Results are cached in
data/raw/media/summaries.json; only names not yet cached are fetched unless
refresh is requested.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from etl.config import MEDIA_RAW_DIR
from etl.extract.media import HEADERS, SLEEP_BETWEEN_CALLS, _get

logger = logging.getLogger(__name__)

SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
EXTRACT_API = "https://en.wikipedia.org/w/api.php"
RANGE_SENTENCES = 2
RANGE_CHARS = 380
CACHE_FILE = "summaries.json"
LICENCE = "CC BY-SA 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
MAX_SENTENCES = 3
DISAMBIGUATIONS = ("lizard", "snake", "reptile", "turtle")
# Wikipedia's short description of a taxon article ("Family of lizards").
_TAXON_DESCRIPTION = re.compile(
    r"\b(?:family|order|suborder|infraorder|superfamily|clade|genus|species|class|group|subfamily)\b"
    r"|lizard|snake|turtle|tortoise|reptile|crocodil|gecko|skink|iguan|chameleon|bird",
    re.IGNORECASE,
)
MAX_CHARS = 520

# A sentence ends at . ! or ? followed by a space and a capital letter, but
# not after a one-letter initial or a common abbreviation ("c.", "approx.").
_SENTENCE_END = re.compile(r"(?<!\b[A-Z])(?<!\bc)(?<!approx)(?<!e\.g)(?<!i\.e)([.!?])\s+(?=[A-Z])")


# Section headings about where a group lives (not its fossil record).
_RANGE_HEADING = re.compile(r"\b(distribution|range|biogeography|geograph\w*)\b", re.IGNORECASE)
_SECTION = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$", re.MULTILINE)
_DISTRIBUTION_VERB = re.compile(
    r"\b(native to|found (?:in|on|throughout|only|across|from)|distributed|occurs? (?:in|on|throughout|across)|"
    r"occurring in|endemic to|ranges? (?:from|across|throughout|over)|is restricted to|lives? in|inhabits?)\b",
    re.IGNORECASE,
)
_PLACE = re.compile(
    r"\b(Africa\w*|Asia\w*|Europe\w*|America\w*|Australia\w*|Oceania|Madagascar|Indonesia|Philippines|"
    r"New Guinea|New Zealand|India|China|Japan|Mexic\w*|Caribbean|Antilles|Andes|Amazon\w*|Brazil|Middle East|"
    r"Arabia\w*|Mediterranean|Pacific|Indian Ocean|Atlantic|Sahara|Borneo|Sri Lanka|Southeast|"
    r"worldwide|every continent|Old World|New World|Neotropic\w*|Indo-\w+|Malay\w*|Socotra|Seychelles)"  # no closing \b: "Indonesian", "Mexican" count too
)


def sections(text: str) -> list[tuple[str, str]]:
    """[(heading, body)] of a plain-text article; the lead has heading ''."""
    out: list[tuple[str, str]] = []
    heading, start = "", 0
    for match in _SECTION.finditer(text):
        out.append((heading, text[start:match.start()].strip()))
        heading, start = match.group(2), match.end()
    out.append((heading, text[start:].strip()))
    return out


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE_END.split(re.sub(r"\s+", " ", text).strip())
    return ["".join(parts[i:i + 2]).strip() for i in range(0, len(parts), 2) if parts[i].strip()]


def _about_places(sentence: str) -> bool:
    return bool(_PLACE.search(sentence)) and "fossil" not in sentence.lower()


def range_from_article(text: str) -> str | None:
    """A sentence or two on where the group lives, or None. Every sentence
    kept names a place, so habitat or research-history text is skipped."""
    parts = [(h, b) for h, b in sections(text) if not re.search(r"fossil|references|external links|further reading", h, re.I)]
    for heading, body in parts:
        if heading and _RANGE_HEADING.search(heading):
            found = [s for s in _sentences(body) if _about_places(s)][:RANGE_SENTENCES]
            if found:
                return undash(trim(" ".join(found), RANGE_SENTENCES, RANGE_CHARS))
    for _, body in parts:
        for sentence in _sentences(body):
            if _DISTRIBUTION_VERB.search(sentence) and _about_places(sentence):
                return undash(trim(sentence, 1, RANGE_CHARS))
    return None


def fetch_article_text(title: str) -> str:
    resp = _get(
        EXTRACT_API,
        params={
            "action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "wiki",
            "titles": title, "redirects": 1, "format": "json", "formatversion": 2,
        },
        headers=HEADERS,
    )
    pages = resp.json().get("query", {}).get("pages") or [{}]
    return pages[0].get("extract") or ""


def fetch_range(summary: dict[str, Any], species: tuple[str, str] | None) -> dict[str, Any] | None:
    """Range text for a summary: from its own article, else from the
    representative species' article (title, url)."""
    text = range_from_article(fetch_article_text(summary["title"]))
    if text:
        # It may repeat a sentence of the summary; the site then shows it once.
        return {"text": text, "scope": "group", "title": summary["title"], "url": summary["url"]}
    if species:
        time.sleep(SLEEP_BETWEEN_CALLS)
        text = range_from_article(fetch_article_text(species[0]))
        if text:
            return {"text": text, "scope": "species", "title": species[0], "url": species[1]}
    return None


def undash(text: str) -> str:
    """Replace em and en dashes: number ranges become 'to', joined words a
    hyphen ('snout-vent'), other dashes commas."""
    text = re.sub(r"(\d)\s*[–—]\s*(\d)", r"\1 to \2", text)
    text = re.sub(r"(?<=[^\W\d])–(?=[^\W\d])", "-", text)
    text = re.sub(r"\s*[–—]\s*", ", ", text)
    return re.sub(r",\s*,", ",", text)


def trim(text: str, max_sentences: int = MAX_SENTENCES, max_chars: int = MAX_CHARS) -> str:
    """The first few whole sentences of ``text``, within ``max_chars`` when possible."""
    text = re.sub(r"\s+", " ", text).strip()
    parts = _SENTENCE_END.split(text)
    sentences = ["".join(parts[i:i + 2]).strip() for i in range(0, len(parts), 2)]
    kept: list[str] = []
    for sentence in sentences[:max_sentences]:
        if kept and len(" ".join(kept + [sentence])) > max_chars:
            break
        kept.append(sentence)
    return " ".join(kept)


def parse_summary(name: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """The summary to keep for ``name``, or None if the page is not about it."""
    if payload.get("type") != "standard":
        return None  # disambiguation pages, missing pages
    extract = payload.get("extract") or ""
    title = payload.get("title") or ""
    # The article must be about the group: it names it, or it is a taxon
    # article (a redirect to an unrelated topic is never shown).
    names_it = name.lower() in f"{title} {extract}".lower()
    if not names_it and not _TAXON_DESCRIPTION.search(payload.get("description") or ""):
        return None
    url = ((payload.get("content_urls") or {}).get("desktop") or {}).get("page")
    if not extract or not url:
        return None
    return {
        "title": title,
        "url": url,
        "extract": undash(trim(extract)),
        "revision": str(payload.get("revision") or "") or None,
        "licence": LICENCE,
        "licence_url": LICENCE_URL,
    }


def _fetch(title: str) -> dict[str, Any] | None:
    try:
        resp = _get(SUMMARY_API.format(title=quote(title.replace(" ", "_"))), params={}, headers=HEADERS)
    except requests.HTTPError as err:
        if err.response is not None and err.response.status_code == 404:
            return None
        raise
    return resp.json()


def fetch_summary(name: str) -> dict[str, Any] | None:
    payload = _fetch(name)
    if payload and payload.get("type") == "disambiguation":
        for sense in DISAMBIGUATIONS:
            payload = _fetch(f"{name} ({sense})")
            if payload and payload.get("type") == "standard":
                break
            time.sleep(SLEEP_BETWEEN_CALLS)
    return parse_summary(name, payload) if payload else None


def cached(path: Path | None = None) -> dict[str, dict[str, Any] | None]:
    path = path or MEDIA_RAW_DIR / CACHE_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def extract(
    names: list[str],
    refresh: bool = False,
    out_dir: Path = MEDIA_RAW_DIR,
    species_articles: dict[str, tuple[str, str]] | None = None,
) -> dict[str, dict[str, Any] | None]:
    """Fetch summaries (and their range text) for ``names``. None records 'no
    usable article', so it is not asked again. ``species_articles`` maps a
    family to its representative species' Wikipedia (title, url), the fallback
    for range text. Saves after every fetch so an interrupted run keeps its
    progress."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / CACHE_FILE
    cache = {} if refresh else cached(path)
    species_articles = species_articles or {}
    todo = [name for name in dict.fromkeys(names) if name not in cache]
    for i, name in enumerate(todo, 1):
        cache[name] = fetch_summary(name)
        logger.info("summary %d/%d %s: %s", i, len(todo), name, "ok" if cache[name] else "none")
        path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        time.sleep(SLEEP_BETWEEN_CALLS)
    missing_range = [n for n in dict.fromkeys(names) if cache.get(n) and "range" not in cache[n]]
    for i, name in enumerate(missing_range, 1):
        cache[name]["range"] = fetch_range(cache[name], species_articles.get(name))
        logger.info("range %d/%d %s: %s", i, len(missing_range), name, (cache[name]["range"] or {}).get("scope", "none"))
        path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        time.sleep(SLEEP_BETWEEN_CALLS)
    return {name: cache.get(name) for name in names}
