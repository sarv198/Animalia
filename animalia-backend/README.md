# Tree of Life Backend

FastAPI service and ETL pipeline for species taxonomy, phylogeny, and search.

## Quick start

```bash
# Start Postgres
docker compose up -d

# Install deps
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure env
cp .env.example .env

# Run migrations
alembic upgrade head

# Start API
uvicorn app.main:app --reload
```

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
| Open Tree of Life | `etl/extract/opentree.py` | Phylogeny |
| GBIF | `etl/extract/gbif.py` | Occurrences / names |
| IUCN | `etl/extract/iucn.py` | Live lookup only — check licensing before redistribution |

## License note (IUCN)

IUCN Red List data is subject to IUCN terms. Prefer live API lookups; do not redistribute bulk dumps without explicit permission.
