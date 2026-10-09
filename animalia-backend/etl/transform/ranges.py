"""Family range maps from GARD 1.7 species ranges.

GARD (Global Assessment of Reptile Distributions; Roll & Meiri 2022, Dryad,
CC0) gives an expert-curated range polygon for each land reptile species. A
family's range is the union of the ranges of its species, where a species
belongs to the family that The Reptile Database checklist puts it in (the same
taxonomy the tree uses). The representative species' own range is kept too.

The result is simplified for display (about a tenth of a degree) and stored as
GeoJSON in WGS84, outer rings clockwise as d3-geo expects. GARD covers land reptiles only: marine species (sea turtles,
sea snakes) have no polygons, so a family's map can be partial or missing; the
number of species mapped is recorded so the site can say so.

The shapefile is not committed (858 MB). Download GARD 1.7 from
https://doi.org/10.5061/dryad.9cnp5hqmb into data/raw/gard/; without it this
step is skipped and the site falls back to GBIF occurrence maps.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from etl.config import GARD_RAW_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)

SOURCE = "GARD 1.7"
CITATION = (
    "Roll, U. & Meiri, S. (2022) GARD 1.7, updated global distributions for all terrestrial reptiles. "
    "Dryad, doi:10.5061/dryad.9cnp5hqmb. Roll et al. 2017, Nat Ecol Evol 1:1677-1682; "
    "Caetano et al. 2022, PLoS Biol 20:e3001544"
)
OUTPUT_FILE = "family_ranges.json"
SPECIES_FIELDS = ("binomial", "Binomial", "BINOMIAL", "sci_name", "SCI_NAME", "species", "Species")
PRE_SIMPLIFY = 0.02  # degrees, applied to each species before the union
SIMPLIFY = 0.1  # degrees, applied to the union
PRECISION = 0.01  # coordinate grid, degrees


@dataclass
class FamilyRange:
    family: str
    species_mapped: int
    range_geojson: dict[str, Any] | None
    rep_scientific_name: str | None
    rep_range_geojson: dict[str, Any] | None


def find_shapefile(directory: Path = GARD_RAW_DIR) -> Path | None:
    matches = sorted(directory.glob("*.shp")) if directory.exists() else []
    return matches[0] if matches else None


def normalise(name: str | None) -> str:
    return " ".join((name or "").replace("_", " ").split()).lower()


def species_field(fields: list[str]) -> str:
    for candidate in SPECIES_FIELDS:
        if candidate in fields:
            return candidate
    raise ValueError(f"no species name field among {fields}")


def assign_families(gard_names: list[str], species_family: dict[str, str]) -> dict[str, list[int]]:
    """Feature indices of GARD per family, matching binomials to the checklist."""
    out: dict[str, list[int]] = {}
    for index, name in enumerate(gard_names):
        family = species_family.get(normalise(name))
        if family:
            out.setdefault(family, []).append(index)
    return out


def to_geojson(geometry) -> dict[str, Any] | None:
    """Simplified, rounded GeoJSON for a shapely geometry (None if empty)."""
    import shapely
    from shapely.geometry import mapping

    if geometry is None or geometry.is_empty:
        return None
    geometry = shapely.simplify(geometry, SIMPLIFY, preserve_topology=True)
    geometry = shapely.set_precision(geometry, PRECISION)
    if geometry.is_empty:
        return None
    # d3-geo (the site's map) reads a clockwise outer ring as "inside";
    # the other winding would fill the rest of the globe instead.
    geometry = shapely.orient_polygons(geometry, exterior_cw=True)
    return json.loads(json.dumps(mapping(geometry)), parse_float=lambda v: round(float(v), 2))


def union(geometries) -> Any:
    import shapely

    parts = [shapely.make_valid(shapely.simplify(g, PRE_SIMPLIFY, preserve_topology=True)) for g in geometries if g is not None]
    parts = [g for g in parts if not g.is_empty]
    if not parts:
        return None
    merged = shapely.union_all(parts, grid_size=PRECISION)
    # make_valid can leave stray lines and points; keep only the areas.
    polygons = [g for g in shapely.get_parts(merged) if g.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(polygons) if polygons else None


def build(
    families: list[str],
    species_family: dict[str, str],
    representatives: dict[str, str],
    shapefile: Path,
) -> dict[str, FamilyRange]:
    """Ranges for ``families``. ``species_family`` maps a normalised binomial
    to its family; ``representatives`` maps a family to its species' name."""
    import pyogrio
    import shapely

    fields = list(pyogrio.read_info(shapefile)["fields"])
    field = species_field(fields)
    _, _, _, (names,) = pyogrio.raw.read(shapefile, read_geometry=False, columns=[field])
    names = [str(n) for n in names]
    by_family = assign_families(names, species_family)
    index_of = {normalise(n): i for i, n in enumerate(names)}
    logger.info("GARD: %d ranges, %d matched to a family in the tree", len(names), sum(len(v) for v in by_family.values()))

    def geometries(indices: list[int]):
        if not indices:
            return []
        _, _, wkb, _ = pyogrio.raw.read(shapefile, fids=indices, columns=[])
        return list(shapely.from_wkb(wkb))

    out: dict[str, FamilyRange] = {}
    for family in families:
        indices = by_family.get(family, [])
        family_range = to_geojson(union(geometries(indices))) if indices else None
        rep = representatives.get(family)
        rep_index = index_of.get(normalise(rep)) if rep else None
        rep_range = to_geojson(union(geometries([rep_index]))) if rep_index is not None else None
        mapped = len({normalise(names[i]) for i in indices})
        out[family] = FamilyRange(family, mapped, family_range, rep, rep_range)
        logger.info("range %s: %d species mapped%s", family, mapped, "" if family_range else " (none)")
    return out


def run(
    families: list[str],
    species_family: dict[str, str],
    representatives: dict[str, str],
    gard_dir: Path = GARD_RAW_DIR,
    out_dir: Path = PROCESSED_DIR,
) -> dict[str, FamilyRange] | None:
    """Build and save the ranges, or return None (with a warning) when the
    GARD shapefile has not been downloaded."""
    shapefile = find_shapefile(gard_dir)
    if shapefile is None:
        logger.warning(
            "GARD shapefile not found in %s; family range maps skipped (download it from %s)",
            gard_dir, "https://doi.org/10.5061/dryad.9cnp5hqmb",
        )
        return None
    ranges = build(families, species_family, representatives, shapefile)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / OUTPUT_FILE).write_text(
        json.dumps({f: asdict(r) for f, r in ranges.items()}), encoding="utf-8"
    )
    return ranges
