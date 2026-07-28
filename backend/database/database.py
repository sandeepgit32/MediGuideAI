import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load database configuration from environment variables
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = os.getenv("MYSQL_PORT")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

# Construct the SQLAlchemy database connection URL for MySQL
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# Create the SQLAlchemy engine that handles the connection pool using
# create_engine(), which manages database connectivity and the connection pool.
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Create a sessionmaker factory for creating new database sessions
# using sessionmaker(). Each session represents a transaction with the database
# and is used to query, insert, update, and delete records.
# Setting autocommit=False requires an explicit commit(), while autoflush=False
# prevents pending changes from being automatically flushed before queries.
# The bind=engine parameter associates the sessions with the configured database engine.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class used for creating SQLAlchemy models
Base = declarative_base()


def get_db():
    """
    Dependency function to provide a database session for each request.
    It uses `yield` instead of `return` because yield allows FastAPI to pause
    the function, pass the session to the endpoint, and then resume execution
    after the request completes. This ensures that db.close() is always
    executed in the finally block, even if the endpoint raises an exception,
    preventing database connection leaks.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
