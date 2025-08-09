from databases import Database
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.DEBUG
)

# Create async database connection
database = Database(settings.DATABASE_URL)

# Create metadata and base class for models
metadata = MetaData()
Base = declarative_base(metadata=metadata)

# Create session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get database session
async def get_database():
    """Get database connection"""
    return database

def get_db_session():
    """Get sync database session for migrations"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()