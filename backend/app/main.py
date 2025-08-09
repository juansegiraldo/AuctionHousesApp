from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import os
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine, get_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Auction Houses API",
    description="The most complete auction houses database in the world",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def initialize_database_if_needed():
    """Initialize database with schema and seed data if needed"""
    try:
        with engine.connect() as connection:
            # Check if tables exist
            check_query = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'auction_houses'
            );
            """)
            
            result = connection.execute(check_query)
            exists = result.scalar()
            
            if exists:
                logger.info("Database already initialized")
                return
            
            logger.info("Initializing database for Render...")
            
            # Create basic table for MVP
            basic_schema = text("""
            CREATE TABLE auction_houses (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                country VARCHAR(100) NOT NULL,
                website VARCHAR(500) NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            
            INSERT INTO auction_houses (name, country, website, description) VALUES
            ('Bogotá Auctions', 'Colombia', 'https://www.bogotaauctions.com', 'Colombian auction house'),
            ('Durán Subastas', 'España', 'https://www.duran-subastas.com', 'Spanish auction house'),
            ('Morton Subastas', 'México', 'https://www.mortonsubastas.com', 'Mexican auction house'),
            ('Christie''s', 'Estados Unidos', 'https://www.christies.com', 'International auction house');
            """)
            
            connection.execute(basic_schema)
            connection.commit()
            logger.info("Database initialized successfully")
            
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

@app.on_event("startup")
async def startup():
    """Initialize database on startup"""
    try:
        # Test database connection
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connected successfully")
        
        # Run database initialization if needed (for Render)
        initialize_database_if_needed()
            
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Auction Houses API",
        "version": "1.0.0",
        "status": "active",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"
        
    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "database": db_status,
        "version": "1.0.0"
    }

# Basic auction houses endpoint
@app.get("/api/v1/houses/")
def get_auction_houses(db: Session = Depends(get_db)):
    """Get all auction houses"""
    try:
        result = db.execute(text("SELECT id, name, country, website, description FROM auction_houses"))
        houses = []
        for row in result:
            houses.append({
                "id": row[0],
                "name": row[1], 
                "country": row[2],
                "website": row[3],
                "description": row[4]
            })
        return houses
    except Exception as e:
        logger.error(f"Error fetching auction houses: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )