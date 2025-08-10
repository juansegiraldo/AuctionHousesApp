from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import declarative_base, sessionmaker
from databases import Database

from app.core.config import settings

# Create database engine (sync only for Render compatibility)
engine = create_engine(
    settings.DATABASE_URL.replace('postgres://', 'postgresql://'),
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.DEBUG
)

# Create metadata and base class for models
metadata = MetaData()
Base = declarative_base(metadata=metadata)

# Create session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create async database connection
database = Database(settings.DATABASE_URL.replace('postgres://', 'postgresql://'))

# Dependency to get database session (sync)
def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency to get async database connection
def get_database() -> Database:
    """Get async database connection"""
    return database