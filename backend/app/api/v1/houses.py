from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from databases import Database

from app.core.database import get_database
from app.models.schemas import AuctionHouse, AuctionHouseCreate, AuctionHouseUpdate
from app.services.houses import HouseService

router = APIRouter()

@router.get("/", response_model=List[AuctionHouse])
async def get_auction_houses(
    country: Optional[str] = Query(None, description="Filter by country"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_database)
):
    """Get all auction houses with optional filters"""
    return await HouseService.get_houses(
        db, 
        country=country, 
        status=status, 
        limit=limit, 
        offset=offset
    )

@router.get("/{house_id}", response_model=AuctionHouse)
async def get_auction_house(
    house_id: int,
    db: Database = Depends(get_database)
):
    """Get auction house by ID"""
    house = await HouseService.get_house_by_id(db, house_id)
    if not house:
        raise HTTPException(status_code=404, detail="Auction house not found")
    return house

@router.post("/", response_model=AuctionHouse, status_code=201)
async def create_auction_house(
    house_data: AuctionHouseCreate,
    db: Database = Depends(get_database)
):
    """Create new auction house"""
    return await HouseService.create_house(db, house_data)

@router.put("/{house_id}", response_model=AuctionHouse)
async def update_auction_house(
    house_id: int,
    house_data: AuctionHouseUpdate,
    db: Database = Depends(get_database)
):
    """Update auction house"""
    house = await HouseService.update_house(db, house_id, house_data)
    if not house:
        raise HTTPException(status_code=404, detail="Auction house not found")
    return house

@router.delete("/{house_id}", status_code=204)
async def delete_auction_house(
    house_id: int,
    db: Database = Depends(get_database)
):
    """Delete auction house"""
    deleted = await HouseService.delete_house(db, house_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Auction house not found")

@router.get("/{house_id}/auctions/", response_model=List[dict])
async def get_house_auctions(
    house_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_database)
):
    """Get auctions for specific house"""
    # Verify house exists
    house = await HouseService.get_house_by_id(db, house_id)
    if not house:
        raise HTTPException(status_code=404, detail="Auction house not found")
    
    return await HouseService.get_house_auctions(db, house_id, limit, offset)

@router.get("/{house_id}/stats/")
async def get_house_stats(
    house_id: int,
    db: Database = Depends(get_database)
):
    """Get statistics for specific house"""
    house = await HouseService.get_house_by_id(db, house_id)
    if not house:
        raise HTTPException(status_code=404, detail="Auction house not found")
    
    return await HouseService.get_house_stats(db, house_id)