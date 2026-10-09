from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL, SERVERLESS
from app.models import Base  # re-export: Alembic + scripts import from here or models

# pool_pre_ping drops connections the database closed while idle (hosted
# Postgres such as Neon suspends when unused). On Vercel each request may run
# in a fresh instance, so no pool is kept; use the provider's pooled URL.
engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    **({"poolclass": NullPool} if SERVERLESS else {}),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

__all__ = ["Base", "SessionLocal", "engine", "get_db"]


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
