from typing import List, Optional, Dict, Any
from databases import Database
from datetime import datetime

from app.models.schemas import Auction, AuctionCreate, AuctionUpdate, AuctionFilters

class AuctionService:
    """Service layer for auctions business logic"""
    
    @staticmethod
    async def get_auctions(
        db: Database,
        filters: AuctionFilters,
        limit: int = 50,
        offset: int = 0
    ) -> List[Auction]:
        """Get auctions with optional filters"""
        
        query = """
            SELECT 
                a.id, a.house_id, a.title, a.description, 
                a.start_date, a.end_date, a.exhibition_start, a.exhibition_end,
                a.status, a.location, a.auction_type, a.slug, a.external_id,
                a.total_lots, a.total_estimate_min, a.total_estimate_max, 
                a.total_realized, a.currency, a.sale_rate,
                a.created_at, a.updated_at,
                h.name as house_name, h.country as house_country
            FROM auctions a
            JOIN auction_houses h ON a.house_id = h.id
            WHERE 1=1
        """
        
        params = {}
        
        if filters.house_id:
            query += " AND a.house_id = :house_id"
            params["house_id"] = filters.house_id
            
        if filters.status:
            query += " AND a.status = :status"
            params["status"] = filters.status
            
        if filters.auction_type:
            query += " AND a.auction_type = :auction_type"
            params["auction_type"] = filters.auction_type
            
        if filters.country:
            query += " AND h.country ILIKE :country"
            params["country"] = f"%{filters.country}%"
            
        if filters.start_date_from:
            query += " AND a.start_date >= :start_date_from"
            params["start_date_from"] = filters.start_date_from
            
        if filters.start_date_to:
            query += " AND a.start_date <= :start_date_to"
            params["start_date_to"] = filters.start_date_to
        
        query += """
            ORDER BY a.start_date DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """
        
        params["limit"] = limit
        params["offset"] = offset
        
        rows = await db.fetch_all(query, params)
        
        return [
            Auction(
                id=row["id"],
                house_id=row["house_id"],
                title=row["title"],
                description=row["description"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                exhibition_start=row["exhibition_start"],
                exhibition_end=row["exhibition_end"],
                status=row["status"],
                location=row["location"],
                auction_type=row["auction_type"],
                slug=row["slug"],
                external_id=row["external_id"],
                total_lots=row["total_lots"] or 0,
                total_estimate_min=row["total_estimate_min"],
                total_estimate_max=row["total_estimate_max"],
                total_realized=row["total_realized"],
                currency=row["currency"],
                sale_rate=row["sale_rate"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                house_name=row["house_name"],
                house_country=row["house_country"]
            )
            for row in rows
        ]
    
    @staticmethod
    async def count_auctions(db: Database, filters: AuctionFilters) -> int:
        """Count auctions with optional filters"""
        
        query = """
            SELECT COUNT(*)
            FROM auctions a
            JOIN auction_houses h ON a.house_id = h.id
            WHERE 1=1
        """
        
        params = {}
        
        if filters.house_id:
            query += " AND a.house_id = :house_id"
            params["house_id"] = filters.house_id
            
        if filters.status:
            query += " AND a.status = :status"
            params["status"] = filters.status
            
        if filters.auction_type:
            query += " AND a.auction_type = :auction_type"
            params["auction_type"] = filters.auction_type
            
        if filters.country:
            query += " AND h.country ILIKE :country"
            params["country"] = f"%{filters.country}%"
            
        if filters.start_date_from:
            query += " AND a.start_date >= :start_date_from"
            params["start_date_from"] = filters.start_date_from
            
        if filters.start_date_to:
            query += " AND a.start_date <= :start_date_to"
            params["start_date_to"] = filters.start_date_to
        
        result = await db.fetch_one(query, params)
        return result[0] if result else 0
    
    @staticmethod
    async def get_auction_by_id(db: Database, auction_id: int) -> Optional[Auction]:
        """Get auction by ID with house information"""
        
        query = """
            SELECT 
                a.id, a.house_id, a.title, a.description, 
                a.start_date, a.end_date, a.exhibition_start, a.exhibition_end,
                a.status, a.location, a.auction_type, a.slug, a.external_id,
                a.total_lots, a.total_estimate_min, a.total_estimate_max, 
                a.total_realized, a.currency, a.sale_rate,
                a.created_at, a.updated_at,
                h.name as house_name, h.country as house_country
            FROM auctions a
            JOIN auction_houses h ON a.house_id = h.id
            WHERE a.id = :auction_id
        """
        
        row = await db.fetch_one(query, {"auction_id": auction_id})
        
        if not row:
            return None
            
        return Auction(
            id=row["id"],
            house_id=row["house_id"],
            title=row["title"],
            description=row["description"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            exhibition_start=row["exhibition_start"],
            exhibition_end=row["exhibition_end"],
            status=row["status"],
            location=row["location"],
            auction_type=row["auction_type"],
            slug=row["slug"],
            external_id=row["external_id"],
            total_lots=row["total_lots"] or 0,
            total_estimate_min=row["total_estimate_min"],
            total_estimate_max=row["total_estimate_max"],
            total_realized=row["total_realized"],
            currency=row["currency"],
            sale_rate=row["sale_rate"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            house_name=row["house_name"],
            house_country=row["house_country"]
        )
    
    @staticmethod
    async def create_auction(db: Database, auction_data: AuctionCreate) -> Auction:
        """Create new auction"""
        
        query = """
            INSERT INTO auctions (
                house_id, title, description, start_date, end_date,
                exhibition_start, exhibition_end, location, auction_type,
                slug, external_id, currency
            )
            VALUES (
                :house_id, :title, :description, :start_date, :end_date,
                :exhibition_start, :exhibition_end, :location, :auction_type,
                :slug, :external_id, :currency
            )
            RETURNING id, house_id, title, description, start_date, end_date,
                      exhibition_start, exhibition_end, status, location,
                      auction_type, slug, external_id, total_lots,
                      total_estimate_min, total_estimate_max, total_realized,
                      currency, sale_rate, created_at, updated_at
        """
        
        params = {
            "house_id": auction_data.house_id,
            "title": auction_data.title,
            "description": auction_data.description,
            "start_date": auction_data.start_date,
            "end_date": auction_data.end_date,
            "exhibition_start": auction_data.exhibition_start,
            "exhibition_end": auction_data.exhibition_end,
            "location": auction_data.location,
            "auction_type": auction_data.auction_type,
            "slug": auction_data.slug,
            "external_id": auction_data.external_id,
            "currency": auction_data.currency
        }
        
        row = await db.fetch_one(query, params)
        
        return Auction(
            id=row["id"],
            house_id=row["house_id"],
            title=row["title"],
            description=row["description"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            exhibition_start=row["exhibition_start"],
            exhibition_end=row["exhibition_end"],
            status=row["status"],
            location=row["location"],
            auction_type=row["auction_type"],
            slug=row["slug"],
            external_id=row["external_id"],
            total_lots=row["total_lots"] or 0,
            total_estimate_min=row["total_estimate_min"],
            total_estimate_max=row["total_estimate_max"],
            total_realized=row["total_realized"],
            currency=row["currency"],
            sale_rate=row["sale_rate"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            house_name=None,  # Would need additional query
            house_country=None
        )
    
    @staticmethod
    async def update_auction(
        db: Database,
        auction_id: int,
        auction_data: AuctionUpdate
    ) -> Optional[Auction]:
        """Update auction"""
        
        # Build dynamic update query
        set_clauses = []
        params = {"auction_id": auction_id}
        
        if auction_data.title is not None:
            set_clauses.append("title = :title")
            params["title"] = auction_data.title
            
        if auction_data.description is not None:
            set_clauses.append("description = :description")
            params["description"] = auction_data.description
            
        if auction_data.start_date is not None:
            set_clauses.append("start_date = :start_date")
            params["start_date"] = auction_data.start_date
            
        if auction_data.end_date is not None:
            set_clauses.append("end_date = :end_date")
            params["end_date"] = auction_data.end_date
            
        if auction_data.status is not None:
            set_clauses.append("status = :status")
            params["status"] = auction_data.status
            
        if auction_data.total_lots is not None:
            set_clauses.append("total_lots = :total_lots")
            params["total_lots"] = auction_data.total_lots
            
        if auction_data.total_realized is not None:
            set_clauses.append("total_realized = :total_realized")
            params["total_realized"] = auction_data.total_realized
        
        if not set_clauses:
            return await AuctionService.get_auction_by_id(db, auction_id)
        
        query = f"""
            UPDATE auctions 
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = :auction_id
        """
        
        result = await db.execute(query, params)
        
        if result == 0:
            return None
            
        return await AuctionService.get_auction_by_id(db, auction_id)
    
    @staticmethod
    async def delete_auction(db: Database, auction_id: int) -> bool:
        """Delete auction and all associated lots"""
        
        # In a production system, you might want to soft delete
        # For now, we'll do cascade delete as defined in the schema
        query = "DELETE FROM auctions WHERE id = :auction_id"
        
        result = await db.execute(query, {"auction_id": auction_id})
        return result > 0
    
    @staticmethod
    async def get_auction_lots(
        db: Database,
        auction_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get lots for specific auction"""
        
        query = """
            SELECT 
                l.id, l.lot_number, l.title, l.description,
                l.estimated_price_min, l.estimated_price_max,
                l.final_price, l.sold, l.currency, l.dimensions,
                l.medium, l.images, l.external_url,
                a.name as artist_name,
                c.name as category_name
            FROM lots l
            LEFT JOIN artists a ON l.artist_id = a.id
            LEFT JOIN categories c ON l.category_id = c.id
            WHERE l.auction_id = :auction_id
            ORDER BY 
                CASE 
                    WHEN l.lot_number ~ '^[0-9]+$' THEN CAST(l.lot_number AS INTEGER)
                    ELSE 999999
                END,
                l.lot_number
            LIMIT :limit OFFSET :offset
        """
        
        rows = await db.fetch_all(query, {
            "auction_id": auction_id,
            "limit": limit,
            "offset": offset
        })
        
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_auction_stats(db: Database, auction_id: int) -> Dict[str, Any]:
        """Get comprehensive statistics for auction"""
        
        # Basic auction stats
        basic_stats_query = """
            SELECT 
                COUNT(l.id) as total_lots,
                COUNT(l.id) FILTER (WHERE l.sold = true) as lots_sold,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_sale_price,
                MIN(l.final_price) FILTER (WHERE l.sold = true) as min_sale_price,
                MAX(l.final_price) FILTER (WHERE l.sold = true) as max_sale_price,
                SUM(l.estimated_price_min) as total_estimate_min,
                SUM(l.estimated_price_max) as total_estimate_max,
                COUNT(DISTINCT l.artist_id) as unique_artists,
                COUNT(DISTINCT l.category_id) as unique_categories
            FROM lots l
            WHERE l.auction_id = :auction_id
        """
        
        basic_stats = await db.fetch_one(basic_stats_query, {"auction_id": auction_id})
        
        # Price ranges
        price_ranges_query = """
            SELECT 
                COUNT(*) FILTER (WHERE l.final_price < 1000) as under_1k,
                COUNT(*) FILTER (WHERE l.final_price BETWEEN 1000 AND 5000) as range_1k_5k,
                COUNT(*) FILTER (WHERE l.final_price BETWEEN 5000 AND 25000) as range_5k_25k,
                COUNT(*) FILTER (WHERE l.final_price BETWEEN 25000 AND 100000) as range_25k_100k,
                COUNT(*) FILTER (WHERE l.final_price >= 100000) as over_100k
            FROM lots l
            WHERE l.auction_id = :auction_id AND l.sold = true
        """
        
        price_ranges = await db.fetch_one(price_ranges_query, {"auction_id": auction_id})
        
        # Top performing lots
        top_lots_query = """
            SELECT 
                l.id, l.lot_number, l.title, l.final_price,
                a.name as artist_name
            FROM lots l
            LEFT JOIN artists a ON l.artist_id = a.id
            WHERE l.auction_id = :auction_id AND l.sold = true
            ORDER BY l.final_price DESC
            LIMIT 10
        """
        
        top_lots = await db.fetch_all(top_lots_query, {"auction_id": auction_id})
        
        # Performance by category
        category_performance_query = """
            SELECT 
                c.name as category_name,
                COUNT(l.id) as total_lots,
                COUNT(l.id) FILTER (WHERE l.sold = true) as sold_lots,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as category_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_price
            FROM lots l
            LEFT JOIN categories c ON l.category_id = c.id
            WHERE l.auction_id = :auction_id
            GROUP BY c.id, c.name
            HAVING COUNT(l.id) > 0
            ORDER BY category_sales DESC NULLS LAST
        """
        
        category_performance = await db.fetch_all(category_performance_query, {"auction_id": auction_id})
        
        return {
            "basic_stats": dict(basic_stats) if basic_stats else {},
            "price_ranges": dict(price_ranges) if price_ranges else {},
            "top_lots": [dict(row) for row in top_lots],
            "category_performance": [dict(row) for row in category_performance],
            "sale_rate": (
                (basic_stats["lots_sold"] / basic_stats["total_lots"] * 100) 
                if basic_stats and basic_stats["total_lots"] and basic_stats["total_lots"] > 0 
                else 0
            )
        }
    
    @staticmethod
    async def get_upcoming_auctions(
        db: Database,
        house_id: Optional[int] = None,
        days_ahead: int = 30,
        limit: int = 50
    ) -> List[Auction]:
        """Get upcoming auctions within specified days"""
        
        query = """
            SELECT 
                a.id, a.house_id, a.title, a.start_date, a.end_date,
                a.location, a.auction_type, a.total_lots,
                h.name as house_name, h.country as house_country
            FROM auctions a
            JOIN auction_houses h ON a.house_id = h.id
            WHERE a.status = 'upcoming'
            AND a.start_date <= NOW() + INTERVAL '%d days'
            AND a.start_date >= NOW()
        """ % days_ahead
        
        params = {"limit": limit}
        
        if house_id:
            query += " AND a.house_id = :house_id"
            params["house_id"] = house_id
        
        query += " ORDER BY a.start_date ASC LIMIT :limit"
        
        rows = await db.fetch_all(query, params)
        
        return [
            Auction(
                id=row["id"],
                house_id=row["house_id"],
                title=row["title"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                location=row["location"],
                auction_type=row["auction_type"],
                total_lots=row["total_lots"] or 0,
                house_name=row["house_name"],
                house_country=row["house_country"],
                # Other fields with defaults
                description=None,
                exhibition_start=None,
                exhibition_end=None,
                status="upcoming",
                slug=None,
                external_id=None,
                total_estimate_min=None,
                total_estimate_max=None,
                total_realized=None,
                currency="USD",
                sale_rate=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            for row in rows
        ]
    
    @staticmethod
    async def get_recent_auctions(
        db: Database,
        limit: int = 20,
        offset: int = 0
    ) -> List[Auction]:
        """Get recently completed auctions ordered by end date"""
        
        query = """
            SELECT 
                a.id, a.house_id, a.title, a.description, 
                a.start_date, a.end_date, a.exhibition_start, a.exhibition_end,
                a.status, a.location, a.auction_type, a.slug, a.external_id,
                a.total_lots, a.total_estimate_min, a.total_estimate_max, 
                a.total_realized, a.currency, a.sale_rate,
                a.created_at, a.updated_at,
                h.name as house_name, h.country as house_country
            FROM auctions a
            JOIN auction_houses h ON a.house_id = h.id
            WHERE a.status = 'completed'
            ORDER BY a.end_date DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """
        
        rows = await db.fetch_all(query, {"limit": limit, "offset": offset})
        
        return [
            Auction(
                id=row["id"],
                house_id=row["house_id"],
                title=row["title"],
                description=row["description"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                exhibition_start=row["exhibition_start"],
                exhibition_end=row["exhibition_end"],
                status=row["status"],
                location=row["location"],
                auction_type=row["auction_type"],
                slug=row["slug"],
                external_id=row["external_id"],
                total_lots=row["total_lots"] or 0,
                total_estimate_min=row["total_estimate_min"],
                total_estimate_max=row["total_estimate_max"],
                total_realized=row["total_realized"],
                currency=row["currency"],
                sale_rate=row["sale_rate"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                house_name=row["house_name"],
                house_country=row["house_country"]
            )
            for row in rows
        ]