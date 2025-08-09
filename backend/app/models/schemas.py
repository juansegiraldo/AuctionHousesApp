from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum

# Enums
class AuctionHouseStatus(str, Enum):
    active = "active"
    inactive = "inactive" 
    maintenance = "maintenance"

class AuctionStatus(str, Enum):
    upcoming = "upcoming"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"

class AuctionType(str, Enum):
    live = "live"
    online = "online"
    hybrid = "hybrid"

class ScrapingTaskStatus(str, Enum):
    started = "started"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"

# Base schemas
class BaseSchema(BaseModel):
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v) if v is not None else None
        }

# Auction House schemas
class AuctionHouseBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    country: str = Field(..., min_length=1, max_length=100) 
    website: HttpUrl
    description: Optional[str] = None
    scraping_config: Optional[Dict[str, Any]] = {}

class AuctionHouseCreate(AuctionHouseBase):
    pass

class AuctionHouseUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    country: Optional[str] = Field(None, min_length=1, max_length=100)
    website: Optional[HttpUrl] = None
    description: Optional[str] = None
    scraping_config: Optional[Dict[str, Any]] = None
    status: Optional[AuctionHouseStatus] = None

class AuctionHouse(AuctionHouseBase):
    id: int
    status: AuctionHouseStatus = AuctionHouseStatus.active
    last_scrape: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Computed fields
    total_auctions: Optional[int] = 0
    total_lots: Optional[int] = 0
    last_auction_date: Optional[datetime] = None

# Artist schemas
class ArtistBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=300)
    birth_year: Optional[int] = Field(None, ge=1000, le=2100)
    death_year: Optional[int] = Field(None, ge=1000, le=2100) 
    nationality: Optional[str] = Field(None, max_length=100)
    movement: Optional[str] = Field(None, max_length=100)
    biography: Optional[str] = None

class ArtistCreate(ArtistBase):
    pass

class Artist(ArtistBase):
    id: int
    verified: bool = False
    created_at: datetime
    updated_at: datetime

# Category schemas  
class CategoryBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=200)
    parent_category_id: Optional[int] = None
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class Category(CategoryBase):
    id: int
    level: int = 0
    created_at: datetime

# Auction schemas
class AuctionBase(BaseSchema):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    exhibition_start: Optional[datetime] = None
    exhibition_end: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=200)
    auction_type: AuctionType = AuctionType.live
    slug: Optional[str] = Field(None, max_length=300)
    external_id: Optional[str] = Field(None, max_length=100)
    currency: str = Field("USD", max_length=3)

class AuctionCreate(AuctionBase):
    house_id: int

class AuctionUpdate(BaseSchema):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[AuctionStatus] = None
    total_lots: Optional[int] = Field(None, ge=0)
    total_realized: Optional[Decimal] = Field(None, ge=0)

class Auction(AuctionBase):
    id: int
    house_id: int
    status: AuctionStatus = AuctionStatus.upcoming
    total_lots: int = 0
    total_estimate_min: Optional[Decimal] = None
    total_estimate_max: Optional[Decimal] = None
    total_realized: Optional[Decimal] = None
    sale_rate: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime
    
    # Related data
    house_name: Optional[str] = None
    house_country: Optional[str] = None

# Lot schemas
class LotBase(BaseSchema):
    lot_number: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=500) 
    description: Optional[str] = None
    estimated_price_min: Optional[Decimal] = Field(None, ge=0)
    estimated_price_max: Optional[Decimal] = Field(None, ge=0)
    dimensions: Optional[str] = Field(None, max_length=200)
    medium: Optional[str] = Field(None, max_length=200)
    provenance: Optional[str] = None
    condition_report: Optional[str] = None
    signature: Optional[str] = None
    external_id: Optional[str] = Field(None, max_length=100)
    external_url: Optional[HttpUrl] = None
    currency: str = Field("USD", max_length=3)

class LotCreate(LotBase):
    auction_id: int
    artist_id: Optional[int] = None
    category_id: Optional[int] = None

class LotUpdate(BaseSchema):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    final_price: Optional[Decimal] = Field(None, ge=0)
    hammer_price: Optional[Decimal] = Field(None, ge=0)
    buyers_premium: Optional[Decimal] = Field(None, ge=0)
    sold: Optional[bool] = None

class Lot(LotBase):
    id: int
    auction_id: int
    artist_id: Optional[int] = None
    category_id: Optional[int] = None
    final_price: Optional[Decimal] = None
    hammer_price: Optional[Decimal] = None
    buyers_premium: Optional[Decimal] = None
    sold: bool = False
    images: List[str] = []
    created_at: datetime
    updated_at: datetime
    
    # Related data
    artist_name: Optional[str] = None
    category_name: Optional[str] = None
    auction_title: Optional[str] = None
    house_name: Optional[str] = None

# Search and filter schemas
class AuctionFilters(BaseSchema):
    house_id: Optional[int] = None
    status: Optional[AuctionStatus] = None
    auction_type: Optional[AuctionType] = None
    country: Optional[str] = None
    start_date_from: Optional[datetime] = None
    start_date_to: Optional[datetime] = None
    
class LotFilters(BaseSchema):
    auction_id: Optional[int] = None
    artist_id: Optional[int] = None
    category_id: Optional[int] = None
    house_id: Optional[int] = None
    sold: Optional[bool] = None
    price_min: Optional[Decimal] = Field(None, ge=0)
    price_max: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)

class SearchQuery(BaseSchema):
    q: str = Field(..., min_length=3, max_length=200)
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)

# Analytics schemas
class SummaryStats(BaseSchema):
    total_houses: int
    total_auctions: int
    total_lots: int
    total_value: Optional[Decimal] = None
    last_update: Optional[datetime] = None

class TrendData(BaseSchema):
    period: str  # 'daily', 'weekly', 'monthly'
    dates: List[str]
    values: List[float]
    
class MarketInsights(BaseSchema):
    top_artists: List[Dict[str, Any]]
    top_categories: List[Dict[str, Any]]
    price_trends: List[TrendData]
    house_performance: List[Dict[str, Any]]

# Response schemas
class PaginatedResponse(BaseSchema):
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int

class ApiResponse(BaseSchema):
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None