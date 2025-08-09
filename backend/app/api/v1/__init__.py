from fastapi import APIRouter
from app.api.v1 import houses, auctions, lots, artists, analytics

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(houses.router, prefix="/houses", tags=["houses"])
api_router.include_router(auctions.router, prefix="/auctions", tags=["auctions"])  
api_router.include_router(lots.router, prefix="/lots", tags=["lots"])
api_router.include_router(artists.router, prefix="/artists", tags=["artists"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])