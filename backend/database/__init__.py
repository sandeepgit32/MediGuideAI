from .database import Base, engine
from . import models  # noqa: F401 — registers all models with SQLAlchemy metadata


def init_db():
    Base.metadata.create_all(bind=engine)
