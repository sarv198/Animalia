"""Load species media (images with credits) and Wikipedia's IUCN status.

Runs after etl/load/to_postgres.py, which resets iucn_category from the CSV;
this step then fills it from Wikipedia, stating the source in iucn_source.
Each species' images are replaced wholesale, so reruns are idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.database import SessionLocal
from app.models import Species, SpeciesMedia


@dataclass
class MediaLoadStats:
    species_with_images: int = 0
    images: int = 0
    species_with_iucn: int = 0
    species_with_wikipedia: int = 0


def iucn_source_text(entry: dict[str, Any]) -> str | None:
    iucn, wiki = entry.get("iucn"), entry.get("wikipedia")
    if not iucn or not wiki:
        return None
    return (
        f"Wikipedia, \"{wiki['title']}\" infobox ({iucn['system']}), "
        f"retrieved {entry['retrieved']}"
    )


def load(media: dict[str, dict[str, Any]]) -> MediaLoadStats:
    stats = MediaLoadStats()
    db = SessionLocal()
    try:
        species_by_name = {s.scientific_name: s for s in db.query(Species).all()}
        unknown = sorted(set(media) - set(species_by_name))
        if unknown:
            raise ValueError(f"media for species not in the database: {unknown}")
        for name, entry in media.items():
            species = species_by_name[name]
            wiki = entry.get("wikipedia")
            iucn = entry.get("iucn")
            species.wikipedia_url = wiki["url"] if wiki else None
            species.iucn_category = iucn["category"] if iucn else None
            species.iucn_assessment_year = iucn.get("year") if iucn else None
            species.iucn_source = iucn_source_text(entry)
            species.media = [
                SpeciesMedia(
                    position=index,
                    source=image["source"],
                    image_url=image["image_url"],
                    thumbnail_url=image.get("thumbnail_url"),
                    page_url=image.get("page_url"),
                    licence=image["licence"],
                    licence_url=image.get("licence_url"),
                    creator=image.get("creator"),
                )
                for index, image in enumerate(entry.get("images", []))
            ]
            stats.images += len(species.media)
            stats.species_with_images += bool(species.media)
            stats.species_with_iucn += bool(iucn)
            stats.species_with_wikipedia += bool(wiki)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return stats


def print_stats(stats: MediaLoadStats, total: int) -> None:
    print(f"media: {stats.images} images for {stats.species_with_images}/{total} species; "
          f"Wikipedia article for {stats.species_with_wikipedia}/{total}; "
          f"IUCN status (from Wikipedia) for {stats.species_with_iucn}/{total}")
