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
    
    # CORS
    ALLOWED_HOSTS: List[str] = ["*"]  # In production, specify exact origins
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()