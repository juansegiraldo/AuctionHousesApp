from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import asyncpg

from app.core.config import settings

# Create sync database engine
engine = create_engine(
    settings.DATABASE_URL.replace('postgresql://', 'postgresql://').replace('postgres://', 'postgresql://'),
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.DEBUG
)

# Create async database engine
async_engine = create_async_engine(
    settings.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://').replace('postgres://', 'postgresql+asyncpg://'),
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.DEBUG
)

# Create metadata and base class for models
metadata = MetaData()
Base = declarative_base(metadata=metadata)

# Create session makers
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# Dependency to get async database session
async def get_async_db():
    """Get async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def get_db_session():
    """Get sync database session for migrations"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()