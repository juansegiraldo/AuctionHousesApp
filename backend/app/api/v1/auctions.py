from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from databases import Database

from app.core.database import get_database
from app.models.schemas import Auction, AuctionCreate, AuctionUpdate, AuctionFilters
from app.services.auctions import AuctionService

router = APIRouter()

@router.get("/", response_model=List[Auction])
async def get_auctions(
    house_id: Optional[int] = Query(None, description="Filter by auction house"),
    status: Optional[str] = Query(None, description="Filter by status"),
    auction_type: Optional[str] = Query(None, description="Filter by auction type"),
    country: Optional[str] = Query(None, description="Filter by country"),
    start_date_from: Optional[datetime] = Query(None, description="Start date from"),
    start_date_to: Optional[datetime] = Query(None, description="Start date to"),
    limit: int = Query(50, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_database)
):
    """Get all auctions with optional filters"""
    filters = AuctionFilters(
        house_id=house_id,
        status=status,
        auction_type=auction_type, 
        country=country,
        start_date_from=start_date_from,
        start_date_to=start_date_to
    )
    
    return await AuctionService.get_auctions(db, filters, limit, offset)

@router.get("/{auction_id}", response_model=Auction)
async def get_auction(
    auction_id: int,
    db: Database = Depends(get_database)
):
    """Get auction by ID"""
    auction = await AuctionService.get_auction_by_id(db, auction_id)
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    return auction

@router.post("/", response_model=Auction, status_code=201)
async def create_auction(
    auction_data: AuctionCreate,
    db: Database = Depends(get_database)
):
    """Create new auction"""
    return await AuctionService.create_auction(db, auction_data)

@router.put("/{auction_id}", response_model=Auction)
async def update_auction(
    auction_id: int,
    auction_data: AuctionUpdate,
    db: Database = Depends(get_database)
):
    """Update auction"""
    auction = await AuctionService.update_auction(db, auction_id, auction_data)
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    return auction

@router.delete("/{auction_id}", status_code=204)
async def delete_auction(
    auction_id: int,
    db: Database = Depends(get_database)
):
    """Delete auction"""
    deleted = await AuctionService.delete_auction(db, auction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Auction not found")

@router.get("/{auction_id}/lots/", response_model=List[dict])
async def get_auction_lots(
    auction_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_database)
):
    """Get lots for specific auction"""
    # Verify auction exists
    auction = await AuctionService.get_auction_by_id(db, auction_id)
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    
    return await AuctionService.get_auction_lots(db, auction_id, limit, offset)

@router.get("/{auction_id}/stats/")
async def get_auction_stats(
    auction_id: int,
    db: Database = Depends(get_database)
):
    """Get statistics for specific auction"""
    auction = await AuctionService.get_auction_by_id(db, auction_id)
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    
    return await AuctionService.get_auction_stats(db, auction_id)