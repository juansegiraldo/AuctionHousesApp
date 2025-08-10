from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from decimal import Decimal
from databases import Database

from app.core.database import get_database
from app.models.schemas import Lot, LotCreate, LotUpdate, LotFilters, SearchQuery
from app.services.lots import LotService

router = APIRouter()

@router.get("/", response_model=List[Lot])
async def get_lots(
    auction_id: Optional[int] = Query(None, description="Filter by auction"),
    artist_id: Optional[int] = Query(None, description="Filter by artist"),
    category_id: Optional[int] = Query(None, description="Filter by category"), 
    house_id: Optional[int] = Query(None, description="Filter by auction house"),
    sold: Optional[bool] = Query(None, description="Filter by sold status"),
    price_min: Optional[Decimal] = Query(None, description="Minimum price", ge=0),
    price_max: Optional[Decimal] = Query(None, description="Maximum price", ge=0),
    currency: Optional[str] = Query(None, description="Currency filter"),
    limit: int = Query(50, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_database)
):
    """Get all lots with optional filters"""
    filters = LotFilters(
        auction_id=auction_id,
        artist_id=artist_id,
        category_id=category_id,
        house_id=house_id,
        sold=sold,
        price_min=price_min,
        price_max=price_max,
        currency=currency
    )
    
    return await LotService.get_lots(db, filters, limit, offset)

@router.get("/search/", response_model=List[Lot])
async def search_lots(
    q: str = Query(..., min_length=3, description="Search query"),
    artist: Optional[str] = Query(None, description="Artist name filter"),
    category: Optional[str] = Query(None, description="Category filter"),
    house: Optional[str] = Query(None, description="Auction house filter"),
    price_min: Optional[Decimal] = Query(None, description="Minimum price", ge=0),
    price_max: Optional[Decimal] = Query(None, description="Maximum price", ge=0),
    limit: int = Query(50, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_database)
):
    """Search lots with full-text search"""
    search_params = {
        "q": q,
        "artist": artist,
        "category": category,
        "house": house,
        "price_min": price_min,
        "price_max": price_max,
        "limit": limit,
        "offset": offset
    }
    
    return await LotService.search_lots(db, search_params)

@router.get("/{lot_id}", response_model=Lot)
async def get_lot(
    lot_id: int,
    db: Database = Depends(get_database)
):
    """Get lot by ID"""
    lot = await LotService.get_lot_by_id(db, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    return lot

@router.post("/", response_model=Lot, status_code=201)
async def create_lot(
    lot_data: LotCreate,
    db: Database = Depends(get_database)
):
    """Create new lot"""
    return await LotService.create_lot(db, lot_data)

@router.put("/{lot_id}", response_model=Lot)
async def update_lot(
    lot_id: int,
    lot_data: LotUpdate,
    db: Database = Depends(get_database)
):
    """Update lot"""
    lot = await LotService.update_lot(db, lot_id, lot_data)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    return lot

@router.delete("/{lot_id}", status_code=204)
async def delete_lot(
    lot_id: int,
    db: Database = Depends(get_database)
):
    """Delete lot"""
    deleted = await LotService.delete_lot(db, lot_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lot not found")

@router.get("/recent/", response_model=List[Lot])
async def get_recent_lots(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_database)
):
    """Get recently added lots"""
    return await LotService.get_recent_lots(db, limit, offset)

@router.get("/similar/{lot_id}/", response_model=List[Lot])
async def get_similar_lots(
    lot_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: Database = Depends(get_database)
):
    """Get lots similar to the specified lot"""
    # Verify lot exists
    lot = await LotService.get_lot_by_id(db, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    
    return await LotService.get_similar_lots(db, lot_id, limit)