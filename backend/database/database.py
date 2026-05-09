import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load database configuration from environment variables
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = os.getenv("MYSQL_PORT")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

# Construct the SQLAlchemy database connection URL for MySQL
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# Create the SQLAlchemy engine that handles the connection pool
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Create a sessionmaker factory for creating new database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class used for creating SQLAlchemy models
Base = declarative_base()


def get_db():
    """
    Dependency function to provide a database session for each request.
    Ensures that the session is properly closed after the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

