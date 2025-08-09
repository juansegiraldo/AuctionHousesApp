from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from databases import Database

from app.core.database import get_database
from app.models.schemas import Artist, ArtistCreate
from app.services.artists import ArtistService

router = APIRouter()

@router.get("/", response_model=List[Artist])
async def get_artists(
    nationality: Optional[str] = Query(None, description="Filter by nationality"),
    movement: Optional[str] = Query(None, description="Filter by art movement"),
    verified: Optional[bool] = Query(None, description="Filter by verified status"),
    limit: int = Query(50, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_database)
):
    """Get all artists with optional filters"""
    return await ArtistService.get_artists(
        db,
        nationality=nationality,
        movement=movement,
        verified=verified,
        limit=limit,
        offset=offset
    )

@router.get("/search/", response_model=List[Artist])
async def search_artists(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_database)
):
    """Search artists by name"""
    return await ArtistService.search_artists(db, q, limit, offset)

@router.get("/{artist_id}", response_model=Artist)
async def get_artist(
    artist_id: int,
    db: Database = Depends(get_database)
):
    """Get artist by ID"""
    artist = await ArtistService.get_artist_by_id(db, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    return artist

@router.post("/", response_model=Artist, status_code=201)
async def create_artist(
    artist_data: ArtistCreate,
    db: Database = Depends(get_database)
):
    """Create new artist"""
    return await ArtistService.create_artist(db, artist_data)

@router.get("/{artist_id}/lots/", response_model=List[dict])
async def get_artist_lots(
    artist_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_database)
):
    """Get lots by specific artist"""
    # Verify artist exists
    artist = await ArtistService.get_artist_by_id(db, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    return await ArtistService.get_artist_lots(db, artist_id, limit, offset)

@router.get("/{artist_id}/stats/")
async def get_artist_stats(
    artist_id: int,
    db: Database = Depends(get_database)
):
    """Get statistics for specific artist"""
    artist = await ArtistService.get_artist_by_id(db, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    return await ArtistService.get_artist_stats(db, artist_id)