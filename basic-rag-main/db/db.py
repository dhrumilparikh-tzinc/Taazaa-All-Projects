from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import get_required_setting

# Create the SQLAlchemy engine for PostgreSQL
engine = create_engine(
    get_required_setting("DATABASE_URL"),
    echo=False,       # set True if you want to see SQL in console
    future=True,
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)

# Base class for ORM models
Base = declarative_base()
