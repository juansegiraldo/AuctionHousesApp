from typing import List, Optional, Dict, Any
from databases import Database
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.schemas import SummaryStats, TrendData, MarketInsights

class AnalyticsService:
    """Service layer for analytics and market insights"""
    
    @staticmethod
    async def get_summary_stats(db: Database) -> SummaryStats:
        """Get overall summary statistics"""
        
        query = """
            SELECT 
                COUNT(DISTINCT h.id) as total_houses,
                COUNT(DISTINCT a.id) as total_auctions,
                COUNT(DISTINCT l.id) as total_lots,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_value,
                MAX(GREATEST(h.last_scrape, a.updated_at, l.updated_at)) as last_update
            FROM auction_houses h
            LEFT JOIN auctions a ON h.id = a.house_id
            LEFT JOIN lots l ON a.id = l.auction_id
        """
        
        row = await db.fetch_one(query)
        
        return SummaryStats(
            total_houses=row["total_houses"] or 0,
            total_auctions=row["total_auctions"] or 0,
            total_lots=row["total_lots"] or 0,
            total_value=row["total_value"],
            last_update=row["last_update"]
        )
    
    @staticmethod
    async def get_price_trends(
        db: Database,
        period: str = "monthly",
        start_date: datetime = None,
        end_date: datetime = None,
        category: Optional[str] = None,
        artist_id: Optional[int] = None,
        house_id: Optional[int] = None
    ) -> List[TrendData]:
        """Get price trends over time"""
        
        # Determine date truncation based on period
        if period == "daily":
            date_trunc = "day"
        elif period == "weekly":
            date_trunc = "week"
        else:
            date_trunc = "month"
        
        query = f"""
            SELECT 
                DATE_TRUNC('{date_trunc}', au.start_date) as period_date,
                COUNT(l.id) FILTER (WHERE l.sold = true) as lots_sold,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_price,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                COUNT(DISTINCT au.id) as auction_count
            FROM lots l
            JOIN auctions au ON l.auction_id = au.id
            JOIN auction_houses h ON au.house_id = h.id
            LEFT JOIN categories c ON l.category_id = c.id
            WHERE l.sold = true
            AND au.start_date BETWEEN :start_date AND :end_date
        """
        
        params = {
            "start_date": start_date or (datetime.utcnow() - timedelta(days=365)),
            "end_date": end_date or datetime.utcnow()
        }
        
        if category:
            query += " AND c.name ILIKE :category"
            params["category"] = f"%{category}%"
            
        if artist_id:
            query += " AND l.artist_id = :artist_id"
            params["artist_id"] = artist_id
            
        if house_id:
            query += " AND h.id = :house_id"
            params["house_id"] = house_id
        
        query += f"""
            GROUP BY DATE_TRUNC('{date_trunc}', au.start_date)
            ORDER BY period_date
        """
        
        rows = await db.fetch_all(query, params)
        
        # Format data for TrendData
        dates = [row["period_date"].strftime("%Y-%m-%d") for row in rows]
        values = [float(row["avg_price"]) if row["avg_price"] else 0.0 for row in rows]
        
        return [TrendData(period=period, dates=dates, values=values)]
    
    @staticmethod
    async def get_volume_trends(
        db: Database,
        period: str = "monthly",
        start_date: datetime = None,
        end_date: datetime = None,
        house_id: Optional[int] = None
    ) -> List[TrendData]:
        """Get auction volume trends"""
        
        if period == "daily":
            date_trunc = "day"
        elif period == "weekly":
            date_trunc = "week"
        else:
            date_trunc = "month"
        
        query = f"""
            SELECT 
                DATE_TRUNC('{date_trunc}', au.start_date) as period_date,
                COUNT(DISTINCT au.id) as auction_count,
                COUNT(l.id) as lot_count,
                COUNT(l.id) FILTER (WHERE l.sold = true) as lots_sold
            FROM auctions au
            LEFT JOIN lots l ON au.id = l.auction_id
            WHERE au.start_date BETWEEN :start_date AND :end_date
        """
        
        params = {
            "start_date": start_date or (datetime.utcnow() - timedelta(days=365)),
            "end_date": end_date or datetime.utcnow()
        }
        
        if house_id:
            query += " AND au.house_id = :house_id"
            params["house_id"] = house_id
        
        query += f"""
            GROUP BY DATE_TRUNC('{date_trunc}', au.start_date)
            ORDER BY period_date
        """
        
        rows = await db.fetch_all(query, params)
        
        # Return multiple trend series
        dates = [row["period_date"].strftime("%Y-%m-%d") for row in rows]
        
        return [
            TrendData(
                period=f"{period}_auctions",
                dates=dates,
                values=[float(row["auction_count"]) for row in rows]
            ),
            TrendData(
                period=f"{period}_lots",
                dates=dates, 
                values=[float(row["lot_count"]) for row in rows]
            ),
            TrendData(
                period=f"{period}_sold",
                dates=dates,
                values=[float(row["lots_sold"]) for row in rows]
            )
        ]
    
    @staticmethod
    async def get_top_artists(
        db: Database,
        metric: str = "total_sales",
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get top performing artists by various metrics"""
        
        # Define metric selection
        if metric == "avg_price":
            order_by = "avg_sale_price DESC"
            having_clause = "HAVING COUNT(l.id) FILTER (WHERE l.sold = true) >= 3"
        elif metric == "lot_count":
            order_by = "lots_sold DESC"
            having_clause = ""
        else:  # total_sales
            order_by = "total_sales DESC"
            having_clause = ""
        
        query = f"""
            SELECT 
                a.id, a.name, a.nationality, a.movement,
                COUNT(l.id) as total_lots,
                COUNT(l.id) FILTER (WHERE l.sold = true) as lots_sold,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_sale_price,
                MAX(l.final_price) FILTER (WHERE l.sold = true) as max_sale_price,
                COUNT(DISTINCT au.id) as auction_appearances
            FROM artists a
            JOIN lots l ON a.id = l.artist_id
            JOIN auctions au ON l.auction_id = au.id
            WHERE au.start_date BETWEEN :start_date AND :end_date
            GROUP BY a.id, a.name, a.nationality, a.movement
            {having_clause}
            ORDER BY {order_by}
            LIMIT :limit
        """
        
        params = {
            "start_date": start_date or (datetime.utcnow() - timedelta(days=365)),
            "end_date": end_date or datetime.utcnow(),
            "limit": limit
        }
        
        rows = await db.fetch_all(query, params)
        
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_top_categories(
        db: Database,
        metric: str = "total_sales",
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        """Get top performing categories"""
        
        if metric == "avg_price":
            order_by = "avg_sale_price DESC"
            having_clause = "HAVING COUNT(l.id) FILTER (WHERE l.sold = true) >= 5"
        elif metric == "lot_count":
            order_by = "lots_sold DESC"
            having_clause = ""
        else:  # total_sales
            order_by = "total_sales DESC"
            having_clause = ""
        
        query = f"""
            SELECT 
                c.id, c.name as category_name, c.parent_category_id,
                COUNT(l.id) as total_lots,
                COUNT(l.id) FILTER (WHERE l.sold = true) as lots_sold,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_sale_price,
                COUNT(DISTINCT l.artist_id) as unique_artists,
                COUNT(DISTINCT au.id) as auction_count
            FROM categories c
            JOIN lots l ON c.id = l.category_id
            JOIN auctions au ON l.auction_id = au.id
            WHERE au.start_date BETWEEN :start_date AND :end_date
            GROUP BY c.id, c.name, c.parent_category_id
            {having_clause}
            ORDER BY {order_by}
            LIMIT :limit
        """
        
        params = {
            "start_date": start_date or (datetime.utcnow() - timedelta(days=365)),
            "end_date": end_date or datetime.utcnow(),
            "limit": limit
        }
        
        rows = await db.fetch_all(query, params)
        
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_house_performance(
        db: Database,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> List[Dict[str, Any]]:
        """Get auction house performance metrics"""
        
        query = """
            SELECT 
                h.id, h.name, h.country,
                COUNT(DISTINCT au.id) as total_auctions,
                COUNT(l.id) as total_lots,
                COUNT(l.id) FILTER (WHERE l.sold = true) as lots_sold,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_sale_price,
                COUNT(DISTINCT l.artist_id) as unique_artists,
                (COUNT(l.id) FILTER (WHERE l.sold = true)::float / 
                 NULLIF(COUNT(l.id), 0) * 100) as sale_rate
            FROM auction_houses h
            LEFT JOIN auctions au ON h.id = au.house_id
            LEFT JOIN lots l ON au.id = l.auction_id
            WHERE au.start_date BETWEEN :start_date AND :end_date
            GROUP BY h.id, h.name, h.country
            HAVING COUNT(DISTINCT au.id) > 0
            ORDER BY total_sales DESC NULLS LAST
        """
        
        params = {
            "start_date": start_date or (datetime.utcnow() - timedelta(days=365)),
            "end_date": end_date or datetime.utcnow()
        }
        
        rows = await db.fetch_all(query, params)
        
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_market_insights(
        db: Database,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> MarketInsights:
        """Get comprehensive market insights"""
        
        # Get all the component data
        top_artists = await AnalyticsService.get_top_artists(
            db, "total_sales", start_date, end_date, 10
        )
        
        top_categories = await AnalyticsService.get_top_categories(
            db, "total_sales", start_date, end_date, 10
        )
        
        price_trends = await AnalyticsService.get_price_trends(
            db, "monthly", start_date, end_date
        )
        
        house_performance = await AnalyticsService.get_house_performance(
            db, start_date, end_date
        )
        
        return MarketInsights(
            top_artists=top_artists,
            top_categories=top_categories,
            price_trends=price_trends,
            house_performance=house_performance
        )
    
    @staticmethod
    async def get_price_predictions(
        db: Database,
        artist_id: Optional[int] = None,
        category_id: Optional[int] = None,
        months_ahead: int = 6
    ) -> Dict[str, Any]:
        """Get price predictions (placeholder for ML implementation)"""
        
        # This is a placeholder implementation
        # In a real system, this would use machine learning models
        
        base_query = """
            SELECT 
                AVG(l.final_price) as avg_price,
                STDDEV(l.final_price) as price_stddev,
                COUNT(l.id) as sample_size,
                MIN(au.start_date) as earliest_date,
                MAX(au.start_date) as latest_date
            FROM lots l
            JOIN auctions au ON l.auction_id = au.id
            WHERE l.sold = true
            AND au.start_date >= NOW() - INTERVAL '24 months'
        """
        
        params = {}
        
        if artist_id:
            base_query += " AND l.artist_id = :artist_id"
            params["artist_id"] = artist_id
            
        if category_id:
            base_query += " AND l.category_id = :category_id"
            params["category_id"] = category_id
        
        row = await db.fetch_one(base_query, params)
        
        if not row or not row["avg_price"] or row["sample_size"] < 5:
            return {
                "prediction": None,
                "confidence": "low",
                "message": "Insufficient data for reliable prediction",
                "sample_size": row["sample_size"] if row else 0
            }
        
        # Simple trend-based prediction (placeholder)
        avg_price = float(row["avg_price"])
        stddev = float(row["price_stddev"] or 0)
        
        # Mock prediction logic - in reality this would be ML-based
        growth_rate = 0.05  # 5% annual growth assumption
        monthly_growth = growth_rate / 12
        
        predicted_price = avg_price * (1 + monthly_growth * months_ahead)
        confidence_interval = stddev * 0.5  # Simplified confidence calculation
        
        return {
            "prediction": {
                "predicted_price": round(predicted_price, 2),
                "price_range": {
                    "min": round(predicted_price - confidence_interval, 2),
                    "max": round(predicted_price + confidence_interval, 2)
                },
                "months_ahead": months_ahead
            },
            "confidence": "medium" if row["sample_size"] >= 20 else "low",
            "historical_data": {
                "avg_price": round(avg_price, 2),
                "sample_size": row["sample_size"],
                "data_period_months": (
                    (row["latest_date"] - row["earliest_date"]).days // 30
                    if row["latest_date"] and row["earliest_date"] else None
                )
            },
            "methodology": "trend_based_placeholder"
        }
    
    @staticmethod
    async def get_seasonal_trends(
        db: Database,
        years: int = 3
    ) -> Dict[str, Any]:
        """Analyze seasonal patterns in auction activity"""
        
        query = """
            SELECT 
                EXTRACT(month FROM au.start_date) as month,
                EXTRACT(quarter FROM au.start_date) as quarter,
                COUNT(DISTINCT au.id) as auction_count,
                COUNT(l.id) as lot_count,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_price
            FROM auctions au
            LEFT JOIN lots l ON au.id = l.auction_id
            WHERE au.start_date >= NOW() - INTERVAL '%d years'
            GROUP BY EXTRACT(month FROM au.start_date), EXTRACT(quarter FROM au.start_date)
            ORDER BY month
        """ % years
        
        rows = await db.fetch_all(query)
        
        monthly_data = {}
        quarterly_data = {}
        
        for row in rows:
            month = int(row["month"])
            quarter = int(row["quarter"])
            
            monthly_data[month] = {
                "auction_count": row["auction_count"],
                "lot_count": row["lot_count"],
                "total_sales": float(row["total_sales"]) if row["total_sales"] else 0,
                "avg_price": float(row["avg_price"]) if row["avg_price"] else 0
            }
            
            if quarter not in quarterly_data:
                quarterly_data[quarter] = {
                    "auction_count": 0,
                    "lot_count": 0,
                    "total_sales": 0
                }
            
            quarterly_data[quarter]["auction_count"] += row["auction_count"]
            quarterly_data[quarter]["lot_count"] += row["lot_count"]
            quarterly_data[quarter]["total_sales"] += float(row["total_sales"]) if row["total_sales"] else 0
        
        return {
            "monthly_trends": monthly_data,
            "quarterly_trends": quarterly_data,
            "analysis_period_years": years
        }
    
    @staticmethod
    async def get_geographic_analysis(db: Database) -> Dict[str, Any]:
        """Analyze market performance by geographic region"""
        
        query = """
            SELECT 
                h.country,
                COUNT(DISTINCT h.id) as house_count,
                COUNT(DISTINCT au.id) as auction_count,
                COUNT(l.id) as lot_count,
                COUNT(l.id) FILTER (WHERE l.sold = true) as lots_sold,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_price
            FROM auction_houses h
            LEFT JOIN auctions au ON h.id = au.house_id
            LEFT JOIN lots l ON au.id = l.auction_id
            WHERE au.start_date >= NOW() - INTERVAL '12 months'
            GROUP BY h.country
            ORDER BY total_sales DESC NULLS LAST
        """
        
        rows = await db.fetch_all(query)
        
        return {
            "by_country": [dict(row) for row in rows],
            "total_countries": len(rows),
            "analysis_period": "12_months"
        }