import os
from contextlib import contextmanager
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False) if engine else None


def get_engine() -> Engine:
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    return engine


def get_sessionmaker() -> sessionmaker[Session]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    return SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    session_factory = get_sessionmaker()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def initialize_database(target_engine: Engine | None = None) -> None:
    """Create database tables for early deployments and demos.

    Production migrations should replace this once Alembic is introduced.
    """
    Base.metadata.create_all(bind=target_engine or get_engine())


def test_connection():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1 as test"))
            print("Successfully connected to Neon Postgres!")
            print("Database is ready for ParlayVu!")
            return True
    except Exception as e:
        print("Connection failed:", str(e))
        return False

if __name__ == "__main__":
    test_connection()