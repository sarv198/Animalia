"""FastAPI entrypoint."""

from collections.abc import Generator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.routers import phylogeny, species, tree

app = FastAPI(title="animalia-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.include_router(tree.router)
app.include_router(species.router)
app.include_router(phylogeny.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
