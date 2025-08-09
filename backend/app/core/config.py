from pydantic import BaseSettings
from typing import List, Optional
import os

class Settings(BaseSettings):
    # API Settings
    PROJECT_NAME: str = "Auction Houses API"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://auction_user:auction_pass@localhost:5432/auction_houses"
    )
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # CORS
    ALLOWED_HOSTS: List[str] = ["*"]  # In production, specify exact origins
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"
    
    # Scraping Settings
    SCRAPING_ENABLED: bool = True
    SCRAPING_USER_AGENT: str = "AuctionHousesBot/1.0"
    SCRAPING_DELAY: float = 1.0  # Delay between requests in seconds
    SCRAPING_TIMEOUT: int = 30   # Request timeout in seconds
    
    # Celery Settings
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL
    
    # Security (to be implemented later)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()