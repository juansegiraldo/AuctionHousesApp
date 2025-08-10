from pydantic_settings import BaseSettings
from typing import List
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
    
    # Celery Configuration
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
    
    # Scraping Configuration
    SCRAPING_USER_AGENT: str = os.getenv(
        "SCRAPING_USER_AGENT", 
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    SCRAPING_TIMEOUT: int = int(os.getenv("SCRAPING_TIMEOUT", "30"))
    SCRAPING_DELAY: float = float(os.getenv("SCRAPING_DELAY", "1.0"))
    
    # CORS
    ALLOWED_HOSTS: List[str] = ["*"]  # In production, specify exact origins
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()