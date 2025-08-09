from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta
from databases import Database

from app.core.database import get_database
from app.models.schemas import SummaryStats, TrendData, MarketInsights
from app.services.analytics import AnalyticsService

router = APIRouter()

@router.get("/summary/", response_model=SummaryStats)
async def get_summary_stats(
    db: Database = Depends(get_database)
):
    """Get overall summary statistics"""
    return await AnalyticsService.get_summary_stats(db)

@router.get("/trends/prices/", response_model=List[TrendData])
async def get_price_trends(
    period: str = Query("monthly", description="Period: daily, weekly, monthly"),
    days: int = Query(365, ge=30, le=1095, description="Days to look back"),
    category: Optional[str] = Query(None, description="Filter by category"),
    artist_id: Optional[int] = Query(None, description="Filter by artist"),
    house_id: Optional[int] = Query(None, description="Filter by house"),
    db: Database = Depends(get_database)
):
    """Get price trends over time"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    return await AnalyticsService.get_price_trends(
        db, period, start_date, end_date, category, artist_id, house_id
    )

@router.get("/trends/volume/", response_model=List[TrendData])
async def get_volume_trends(
    period: str = Query("monthly", description="Period: daily, weekly, monthly"),
    days: int = Query(365, ge=30, le=1095, description="Days to look back"),
    house_id: Optional[int] = Query(None, description="Filter by house"),
    db: Database = Depends(get_database)
):
    """Get auction volume trends"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    return await AnalyticsService.get_volume_trends(
        db, period, start_date, end_date, house_id
    )

@router.get("/top-artists/")
async def get_top_artists(
    metric: str = Query("total_sales", description="Metric: total_sales, avg_price, lot_count"),
    period_days: int = Query(365, ge=30, le=1095),
    limit: int = Query(20, ge=5, le=100),
    db: Database = Depends(get_database)
):
    """Get top performing artists"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=period_days)
    
    return await AnalyticsService.get_top_artists(db, metric, start_date, end_date, limit)

@router.get("/top-categories/")
async def get_top_categories(
    metric: str = Query("total_sales", description="Metric: total_sales, avg_price, lot_count"),
    period_days: int = Query(365, ge=30, le=1095),
    limit: int = Query(15, ge=5, le=50),
    db: Database = Depends(get_database)
):
    """Get top performing categories"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=period_days)
    
    return await AnalyticsService.get_top_categories(db, metric, start_date, end_date, limit)

@router.get("/house-performance/")
async def get_house_performance(
    period_days: int = Query(365, ge=30, le=1095),
    db: Database = Depends(get_database)
):
    """Get auction house performance metrics"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=period_days)
    
    return await AnalyticsService.get_house_performance(db, start_date, end_date)

@router.get("/market-insights/", response_model=MarketInsights)
async def get_market_insights(
    period_days: int = Query(365, ge=90, le=1095),
    db: Database = Depends(get_database)
):
    """Get comprehensive market insights"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=period_days)
    
    return await AnalyticsService.get_market_insights(db, start_date, end_date)

@router.get("/predictions/prices/")
async def get_price_predictions(
    artist_id: Optional[int] = Query(None, description="Artist to predict"),
    category_id: Optional[int] = Query(None, description="Category to predict"),
    months_ahead: int = Query(6, ge=1, le=24, description="Months to predict ahead"),
    db: Database = Depends(get_database)
):
    """Get price predictions (placeholder for ML implementation)"""
    return await AnalyticsService.get_price_predictions(
        db, artist_id, category_id, months_ahead
    )