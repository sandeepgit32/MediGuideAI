import logging

from sqlalchemy import text

from .database import Base, engine
from . import models  # noqa: F401 — registers all models with SQLAlchemy metadata

logger = logging.getLogger(__name__)


def init_db():
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """Apply incremental schema changes that SQLAlchemy create_all cannot handle."""
    with engine.connect() as conn:
        # Add summary column to consultation_history if it doesn't exist yet
        try:
            conn.execute(
                text("ALTER TABLE consultation_history ADD COLUMN summary TEXT NULL")
            )
            conn.commit()
            logger.info("Migration: added 'summary' column to consultation_history")
        except Exception:
            # Column already exists — nothing to do
            conn.rollback()

        # Drop the patient_profiles table if it still exists from an older schema
        try:
            conn.execute(text("DROP TABLE IF EXISTS patient_profiles"))
            conn.commit()
            logger.info("Migration: dropped legacy 'patient_profiles' table")
        except Exception:
            conn.rollback()
