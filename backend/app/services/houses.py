from typing import List, Optional, Dict, Any
from databases import Database
from datetime import datetime

from app.models.schemas import AuctionHouse, AuctionHouseCreate, AuctionHouseUpdate

class HouseService:
    """Service layer for auction houses business logic"""
    
    @staticmethod
    async def get_houses(
        db: Database, 
        country: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[AuctionHouse]:
        """Get auction houses with optional filters"""
        
        query = """
            SELECT 
                h.id, h.name, h.country, h.website, h.description,
                h.scraping_config, h.last_scrape, h.status, 
                h.created_at, h.updated_at,
                COUNT(DISTINCT a.id) as total_auctions,
                COUNT(DISTINCT l.id) as total_lots,
                MAX(a.start_date) as last_auction_date
            FROM auction_houses h
            LEFT JOIN auctions a ON h.id = a.house_id
            LEFT JOIN lots l ON a.id = l.auction_id
            WHERE 1=1
        """
        
        params = {}
        
        if country:
            query += " AND h.country ILIKE :country"
            params["country"] = f"%{country}%"
            
        if status:
            query += " AND h.status = :status"  
            params["status"] = status
            
        query += """
            GROUP BY h.id, h.name, h.country, h.website, h.description,
                     h.scraping_config, h.last_scrape, h.status, 
                     h.created_at, h.updated_at
            ORDER BY h.name
            LIMIT :limit OFFSET :offset
        """
        
        params["limit"] = limit
        params["offset"] = offset
        
        rows = await db.fetch_all(query, params)
        
        return [
            AuctionHouse(
                id=row["id"],
                name=row["name"],
                country=row["country"],
                website=row["website"],
                description=row["description"],
                scraping_config=row["scraping_config"] or {},
                last_scrape=row["last_scrape"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                total_auctions=row["total_auctions"] or 0,
                total_lots=row["total_lots"] or 0,
                last_auction_date=row["last_auction_date"]
            )
            for row in rows
        ]
    
    @staticmethod
    async def get_house_by_id(db: Database, house_id: int) -> Optional[AuctionHouse]:
        """Get auction house by ID with computed fields"""
        
        query = """
            SELECT 
                h.id, h.name, h.country, h.website, h.description,
                h.scraping_config, h.last_scrape, h.status, 
                h.created_at, h.updated_at,
                COUNT(DISTINCT a.id) as total_auctions,
                COUNT(DISTINCT l.id) as total_lots,
                MAX(a.start_date) as last_auction_date
            FROM auction_houses h
            LEFT JOIN auctions a ON h.id = a.house_id
            LEFT JOIN lots l ON a.id = l.auction_id
            WHERE h.id = :house_id
            GROUP BY h.id, h.name, h.country, h.website, h.description,
                     h.scraping_config, h.last_scrape, h.status, 
                     h.created_at, h.updated_at
        """
        
        row = await db.fetch_one(query, {"house_id": house_id})
        
        if not row:
            return None
            
        return AuctionHouse(
            id=row["id"],
            name=row["name"],
            country=row["country"],
            website=row["website"],
            description=row["description"],
            scraping_config=row["scraping_config"] or {},
            last_scrape=row["last_scrape"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            total_auctions=row["total_auctions"] or 0,
            total_lots=row["total_lots"] or 0,
            last_auction_date=row["last_auction_date"]
        )
    
    @staticmethod
    async def create_house(db: Database, house_data: AuctionHouseCreate) -> AuctionHouse:
        """Create new auction house"""
        
        query = """
            INSERT INTO auction_houses (name, country, website, description, scraping_config)
            VALUES (:name, :country, :website, :description, :scraping_config)
            RETURNING id, name, country, website, description, scraping_config, 
                      last_scrape, status, created_at, updated_at
        """
        
        params = {
            "name": house_data.name,
            "country": house_data.country,
            "website": str(house_data.website),
            "description": house_data.description,
            "scraping_config": house_data.scraping_config
        }
        
        row = await db.fetch_one(query, params)
        
        return AuctionHouse(
            id=row["id"],
            name=row["name"],
            country=row["country"],
            website=row["website"],
            description=row["description"],
            scraping_config=row["scraping_config"] or {},
            last_scrape=row["last_scrape"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            total_auctions=0,
            total_lots=0,
            last_auction_date=None
        )
    
    @staticmethod
    async def update_house(
        db: Database, 
        house_id: int, 
        house_data: AuctionHouseUpdate
    ) -> Optional[AuctionHouse]:
        """Update auction house"""
        
        # Build dynamic update query
        set_clauses = []
        params = {"house_id": house_id}
        
        if house_data.name is not None:
            set_clauses.append("name = :name")
            params["name"] = house_data.name
            
        if house_data.country is not None:
            set_clauses.append("country = :country")
            params["country"] = house_data.country
            
        if house_data.website is not None:
            set_clauses.append("website = :website")
            params["website"] = str(house_data.website)
            
        if house_data.description is not None:
            set_clauses.append("description = :description")
            params["description"] = house_data.description
            
        if house_data.scraping_config is not None:
            set_clauses.append("scraping_config = :scraping_config")
            params["scraping_config"] = house_data.scraping_config
            
        if house_data.status is not None:
            set_clauses.append("status = :status")
            params["status"] = house_data.status
        
        if not set_clauses:
            # No fields to update, return current house
            return await HouseService.get_house_by_id(db, house_id)
        
        query = f"""
            UPDATE auction_houses 
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = :house_id
            RETURNING id, name, country, website, description, scraping_config, 
                      last_scrape, status, created_at, updated_at
        """
        
        row = await db.fetch_one(query, params)
        
        if not row:
            return None
            
        return AuctionHouse(
            id=row["id"],
            name=row["name"],
            country=row["country"],
            website=row["website"],
            description=row["description"],
            scraping_config=row["scraping_config"] or {},
            last_scrape=row["last_scrape"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            total_auctions=0,  # Would need additional query
            total_lots=0,      # Would need additional query
            last_auction_date=None
        )
    
    @staticmethod
    async def delete_house(db: Database, house_id: int) -> bool:
        """Delete auction house (soft delete by setting status to inactive)"""
        
        query = """
            UPDATE auction_houses 
            SET status = 'inactive', updated_at = NOW()
            WHERE id = :house_id AND status = 'active'
        """
        
        result = await db.execute(query, {"house_id": house_id})
        return result > 0
    
    @staticmethod
    async def get_house_auctions(
        db: Database, 
        house_id: int, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get auctions for specific house"""
        
        query = """
            SELECT 
                a.id, a.title, a.description, a.start_date, a.end_date,
                a.status, a.location, a.auction_type, a.total_lots,
                a.total_realized, a.currency, a.created_at
            FROM auctions a
            WHERE a.house_id = :house_id
            ORDER BY a.start_date DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """
        
        rows = await db.fetch_all(query, {
            "house_id": house_id,
            "limit": limit,
            "offset": offset
        })
        
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_house_stats(db: Database, house_id: int) -> Dict[str, Any]:
        """Get comprehensive statistics for auction house"""
        
        # Basic counts
        basic_stats_query = """
            SELECT 
                COUNT(DISTINCT a.id) as total_auctions,
                COUNT(DISTINCT l.id) as total_lots,
                COUNT(DISTINCT l.id) FILTER (WHERE l.sold = true) as lots_sold,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_sale_price,
                MAX(a.start_date) as last_auction_date,
                COUNT(DISTINCT l.artist_id) as unique_artists
            FROM auction_houses h
            LEFT JOIN auctions a ON h.id = a.house_id
            LEFT JOIN lots l ON a.id = l.auction_id
            WHERE h.id = :house_id
        """
        
        basic_stats = await db.fetch_one(basic_stats_query, {"house_id": house_id})
        
        # Recent activity (last 30 days)
        recent_activity_query = """
            SELECT 
                COUNT(DISTINCT a.id) as recent_auctions,
                COUNT(DISTINCT l.id) as recent_lots,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as recent_sales
            FROM auctions a
            LEFT JOIN lots l ON a.id = l.auction_id
            WHERE a.house_id = :house_id 
            AND a.start_date >= NOW() - INTERVAL '30 days'
        """
        
        recent_activity = await db.fetch_one(recent_activity_query, {"house_id": house_id})
        
        # Top categories
        top_categories_query = """
            SELECT 
                c.name as category_name,
                COUNT(l.id) as lot_count,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as category_sales
            FROM lots l
            JOIN auctions a ON l.auction_id = a.id
            LEFT JOIN categories c ON l.category_id = c.id
            WHERE a.house_id = :house_id AND l.sold = true
            GROUP BY c.id, c.name
            ORDER BY category_sales DESC NULLS LAST
            LIMIT 5
        """
        
        top_categories = await db.fetch_all(top_categories_query, {"house_id": house_id})
        
        return {
            "basic_stats": dict(basic_stats) if basic_stats else {},
            "recent_activity": dict(recent_activity) if recent_activity else {},
            "top_categories": [dict(row) for row in top_categories],
            "sale_rate": (
                (basic_stats["lots_sold"] / basic_stats["total_lots"] * 100) 
                if basic_stats and basic_stats["total_lots"] and basic_stats["total_lots"] > 0 
                else 0
            )
        }
    
    @staticmethod
    async def update_last_scrape(db: Database, house_id: int) -> bool:
        """Update last scrape timestamp for house"""
        
        query = """
            UPDATE auction_houses 
            SET last_scrape = NOW(), updated_at = NOW()
            WHERE id = :house_id
        """
        
        result = await db.execute(query, {"house_id": house_id})
        return result > 0