# Tree of Life Backend

FastAPI service and ETL pipeline for species taxonomy, phylogeny, and search.

## Quick start

```bash
# Start Postgres
docker compose up -d

# Install deps
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt   # app deps + pytest/httpx

# Configure env
cp .env.example .env

# Run migrations
alembic upgrade head

# Load data + build and date the phylogeny + run checks
python etl/run_pipeline.py                     # reuses cached Open Tree / TimeTree data
python etl/run_pipeline.py --refresh-opentree  # re-download from Open Tree
python etl/run_pipeline.py --refresh-timetree  # re-query TimeTree

# Tests (database tests run when the pipeline has been loaded)
python -m pytest

# Start API
uvicorn app.main:app --reload
```

## Phylogeny

`GET /api/phylogeny/reptiles` returns one nested tree rooted at Reptilia. It is
separate from `GET /api/tree/reptiles`, which is the classification
(clade → family), not an evolutionary tree.

How it is built (`etl/run_pipeline.py`):

1. **Open Tree of Life** (`etl/extract/opentree.py`) — the induced subtree of
   every representative species' `ott_id` gives the branching order inside
   Lepidosauria, Testudines and Crocodylia. Responses are cached in
   `data/raw/opentree/`; the synthesis version is pinned in
   `data/metadata/source_versions.json`.
2. **Curated backbone** (`data/curated/reptile_backbone.csv`) — everything above
   those groups, including extinct groups Open Tree cannot place (mesosaurs,
   pterosaurs, dinosaurs) and birds. Each row cites its source. Living groups are
   anchored as the common ancestor of two families. The build fails if the
   backbone contradicts Open Tree.
3. **Family check** (`etl/transform/family_check.py`) — each family tip is
   placed by one representative species, so every family is checked as a whole:
   all the species The Reptile Database assigns to it are located in Open Tree's
   tree. `placement_status` is `confirmed` (they form one branch), `flagged`
   (they do not; the tip's `note` says how many form the main branch, which
   species sit elsewhere and which other families intrude), or `unknown` (none
   of its species are in Open Tree's tree). Only evidence counts: species that
   Open Tree places by taxonomy alone (in no published tree) are set aside, and
   the note says how many. `data/curated/family_status_overrides.csv` sets a
   status by hand where Open Tree's input trees are outdated (each with a reason
   and citation). The pipeline also reports any representative outside its
   family's main branch, or placed by taxonomy alone: both are reasons to swap it
   in `data/curated/reptile_family_representatives.csv`.
4. **Clade names** (`data/curated/clade_names.csv`) — names for well-known clades
   Open Tree leaves unnamed (Toxicofera, Pleurodonta, ...), each defined as the
   common ancestor of two families. The build fails rather than overwrite a name.

### Node ages

Every node has an `age_ma` (millions of years ago) and an `age_source`
(`etl/transform/date_phylogeny.py`). The API also gives each node
`stem_age_ma`, its parent's age: when that lineage split from its closest
relatives.

| `age_source` | Used for | From |
|---|---|---|
| `present` | living family tips, living groups (Aves) | 0 Ma |
| `last appearance` | extinct groups | `data/curated/fossil_dates.csv` (first fossil kept in `first_appearance_ma`) |
| `fossil minimum` | nodes only fossils can date (Reptilia, Avemetatarsalia, Dinosauria, Saurischia), and Squamata (170 Ma, raised to meet the molecular dates inside it) | `data/curated/fossil_dates.csv` |
| `TimeTree 5` | every other split | median of published molecular estimates, with confidence interval and study count; cached in `data/raw/timetree/` |
| `interpolated` | splits TimeTree has no estimate for | halfway between parent and oldest dated descendant |

Consistency is enforced: no ancestor is younger than a descendant or than an
extinct descendant's first fossil. Two TimeTree estimates that clearly clash
(confidence intervals do not overlap) are resolved by discarding the one with
fewer supporting studies; smaller clashes and clashes with fossils raise the
ancestor. Every change sets `age_adjusted` and keeps the original estimate in
`age_unadjusted_ma`; the pipeline prints what it changed.

Fossil dates are hand-curated with citations because PBDB's raw ranges contain
misdated and misassigned records. To compare them with PBDB again:

```bash
python scripts/review_fossil_dates.py
```

### Species images and conservation status

`etl/extract/media.py` (pipeline step 7, cached in `data/raw/media/`) collects,
per representative species: the English Wikipedia article, its lead image (only
if it is on Wikimedia Commons with an open licence) and a few GBIF occurrence
photos (mostly iNaturalist). Images are linked, not copied; each keeps its
creator, licence and source page, and the UI shows that credit. Allowed
licences: CC0, public domain, CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA (no
"no-derivatives"). **Most GBIF photos are CC BY-NC: fine for a non-commercial
site; filter them out before any commercial use.**

The IUCN Red List category is read from the Wikipedia article's infobox (only
when its status system is IUCN), so it is Wikipedia's statement of the IUCN
category, labelled as such with the retrieval date. Wikimedia requires API
clients to give a contact: set `WIKIMEDIA_CONTACT` (a URL or email) in `.env`;
it defaults to the project's GitHub URL. Re-fetch with `--refresh-media`.

### Reptile Database checklist

The checklist is the authority for family names and family membership: the
representative species' families follow it, and the family check uses it.
`python -m etl.extract.reptiledb` downloads it to `data/raw/reptiledb/` and pins
its release; the Open Tree extract does this automatically.

Cite it as (the accessed date is when the checklist was downloaded;
`etl.extract.reptiledb.citation()` produces it):

> Uetz, P., Freed, P., Aguilar, R., Reyes, F., Kudera, J. & Hošek, J. (eds.) (2026)
> The Reptile Database, http://www.reptile-database.org, accessed 3 October 2026

## Layout

- `app/` — FastAPI web API (routers, CRUD, ORM models, Pydantic schemas)
- `etl/` — extract → transform → validate → load pipeline
- `data/` — raw downloads, processed Parquet, source version metadata
- `scripts/` — curation and DB seeding helpers
- `tests/` — API and ETL tests

## Data sources

| Source | Module | Notes |
|--------|--------|-------|
| Catalogue of Life | `etl/extract/col.py` | COL XR via ChecklistBank |
| Open Tree of Life | `etl/extract/opentree.py` | Phylogeny of living families |
| Curated backbone | `data/curated/reptile_backbone.csv` | Deep relationships + extinct groups, cited per row |
| TimeTree 5 | `etl/extract/timetree.py` | Divergence times of living groups (Kumar et al. 2022) |
| Curated fossil dates | `data/curated/fossil_dates.csv` | Fossil ranges + minimum ages, cited per row; reviewed against PBDB |
| The Reptile Database | `etl/extract/reptiledb.py` | Family names and membership (Uetz et al. 2026); used by the family check |
| Wikipedia / Wikimedia Commons | `etl/extract/media.py` | Species article, lead image (with licence), IUCN category as stated in the infobox |
| GBIF occurrence media | `etl/extract/media.py` | Openly licensed species photos (mostly iNaturalist) |
| GBIF | `etl/extract/gbif.py` | Occurrences / names |
| IUCN | `etl/extract/iucn.py` | Live lookup only — check licensing before redistribution |

## License note (IUCN)

IUCN Red List data is subject to IUCN terms. Prefer live API lookups; do not redistribute bulk dumps without explicit permission.
