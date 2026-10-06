"""TimeTree 5 divergence times (Kumar et al. 2022, Mol Biol Evol 39:msac174).

TimeTree identifies taxa by NCBI taxonomy id. For two taxa it returns the age
of their most recent common ancestor: the median of published molecular
estimates with a confidence interval.

We call /mrca/id/{a}+{b}/json rather than /pairwise: it reports which ids it
could not find instead of silently swapping in a relative, and it carries the
TimeTree data version. An answer with any missing id is treated as no answer.

Responses are cached in data/raw/timetree/mrca.json so reruns are offline and
reproducible; only pairs not yet cached hit the network.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from etl.config import METADATA_PATH, TIMETREE_API_BASE, TIMETREE_RAW_DIR

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 60
SLEEP_BETWEEN_CALLS = 0.5  # free academic API; be polite
CACHE_FILE = "mrca.json"


@dataclass(frozen=True)
class DivergenceEstimate:
    age_ma: float
    ci_low: float | None
    ci_high: float | None
    study_count: int
    version: str | None


def _count_estimates(raw: Any) -> int:
    """time_estimates arrives as a Postgres-style array string: '{179,140,221.49}'."""
    if isinstance(raw, list):
        return len(raw)
    text = str(raw or "").strip("{} ")
    return len([v for v in text.split(",") if v.strip()]) if text else 0


def parse_mrca(body: dict[str, Any], a: int, b: int) -> DivergenceEstimate | None:
    """The estimate in one /mrca response, or None if TimeTree could not answer
    for exactly these two taxa."""
    if body.get("missing_ids"):
        return None
    if set(body.get("found_ids") or []) != {a, b}:
        return None
    # precomputed_age is the median of published estimates and matches the CI.
    # adjusted_age is smoothed to fit TimeTree's own tree, which can differ from
    # ours, so it is only a fallback; date_phylogeny enforces consistency itself.
    age = body.get("precomputed_age")
    if age is None:
        age = body.get("adjusted_age")
    if age is None:
        return None
    version = body.get("version")
    return DivergenceEstimate(
        age_ma=float(age),
        ci_low=_float_or_none(body.get("precomputed_ci_low")),
        ci_high=_float_or_none(body.get("precomputed_ci_high")),
        study_count=_count_estimates(body.get("time_estimates")),
        version=str(version) if version is not None else None,
    )


def _float_or_none(value: Any) -> float | None:
    return None if value is None else float(value)


class TimeTreeClient:
    """Cached lookups of divergence times between two NCBI taxa."""

    def __init__(self, cache_dir: Path = TIMETREE_RAW_DIR, refresh: bool = False) -> None:
        self.cache_path = cache_dir / CACHE_FILE
        self.refresh = refresh
        self.cache: dict[str, dict[str, Any]] = {}
        if self.cache_path.exists():
            self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self._fetched: set[str] = set()
        self.network_calls = 0

    @staticmethod
    def key(a: int, b: int) -> str:
        low, high = sorted((a, b))
        return f"{low}+{high}"

    def divergence(self, a: int, b: int) -> DivergenceEstimate | None:
        if a == b:
            return None
        key = self.key(a, b)
        stale = self.refresh and key not in self._fetched
        if key not in self.cache or stale:
            self.cache[key] = self._fetch(key)
            self._fetched.add(key)
        entry = self.cache[key]
        if entry["status_code"] != 200:
            return None
        return parse_mrca(entry["body"], a, b)

    def _fetch(self, key: str) -> dict[str, Any]:
        url = f"{TIMETREE_API_BASE}/mrca/id/{key}/json"
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        self.network_calls += 1
        time.sleep(SLEEP_BETWEEN_CALLS)
        if resp.status_code >= 500:
            resp.raise_for_status()  # transient; do not cache
        try:
            body = resp.json()
        except ValueError:
            body = {"message": resp.text[:500]}
        return {"status_code": resp.status_code, "body": body}

    def versions(self) -> set[str]:
        """TimeTree data versions seen in the cached answers."""
        return {
            str(entry["body"]["version"])
            for entry in self.cache.values()
            if isinstance(entry.get("body"), dict) and entry["body"].get("version") is not None
        }

    def save(self) -> None:
        """Write the cache and pin the TimeTree data version(s) in source_versions.json."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=1, sort_keys=True), encoding="utf-8")
        versions = sorted(self.versions())
        if versions:
            pinned = json.loads(METADATA_PATH.read_text(encoding="utf-8")) if METADATA_PATH.exists() else {}
            pinned["timetree"] = ",".join(versions)
            METADATA_PATH.write_text(json.dumps(pinned, indent=2) + "\n", encoding="utf-8")
