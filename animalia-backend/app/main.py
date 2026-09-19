"""FastAPI entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import search, species, taxa, tree

API_PREFIX = "/api/v1"
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]

app = FastAPI(title="animalia-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(species.router, prefix=API_PREFIX)
app.include_router(taxa.router, prefix=API_PREFIX)
app.include_router(tree.router, prefix=API_PREFIX)
app.include_router(search.router, prefix=API_PREFIX)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
