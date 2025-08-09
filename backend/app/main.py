from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import os
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine, database
from app.api.v1 import api_router

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

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

async def initialize_database_if_needed():
    """Initialize database with schema and seed data if needed"""
    try:
        # Check if tables exist
        check_query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'auction_houses'
        );
        """
        
        exists = await database.fetch_val(check_query)
        if exists:
            logger.info("Database already initialized")
            return
        
        logger.info("Initializing database for Railway...")
        
        # This is a simplified initialization for Railway
        # In production, you'd want to run migrations separately
        basic_schema = """
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
        """
        
        await database.execute(text(basic_schema))
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

@app.on_event("startup")
async def startup():
    """Connect to database on startup"""
    try:
        await database.connect()
        logger.info("Database connected successfully")
        
        # Run database initialization if needed (for Railway)
        if os.getenv("RAILWAY_ENVIRONMENT") and not os.getenv("DB_INITIALIZED"):
            await initialize_database_if_needed()
            
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        # In production, we might want to continue without DB for health checks

@app.on_event("shutdown") 
async def shutdown():
    """Disconnect from database on shutdown"""
    await database.disconnect()
    logger.info("Database disconnected")

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
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        await database.fetch_one("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"
        
    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "database": db_status,
        "version": "1.0.0"
    }

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