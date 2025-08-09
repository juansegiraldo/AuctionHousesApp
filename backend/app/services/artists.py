from typing import List, Optional, Dict, Any
from databases import Database

from app.models.schemas import Artist, ArtistCreate

class ArtistService:
    """Service layer for artists business logic"""
    
    @staticmethod
    async def get_artists(
        db: Database,
        nationality: Optional[str] = None,
        movement: Optional[str] = None,
        verified: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Artist]:
        """Get artists with optional filters"""
        
        query = """
            SELECT 
                id, name, birth_year, death_year, nationality, movement,
                biography, verified, created_at, updated_at
            FROM artists
            WHERE 1=1
        """
        
        params = {}
        
        if nationality:
            query += " AND nationality ILIKE :nationality"
            params["nationality"] = f"%{nationality}%"
            
        if movement:
            query += " AND movement ILIKE :movement"
            params["movement"] = f"%{movement}%"
            
        if verified is not None:
            query += " AND verified = :verified"
            params["verified"] = verified
        
        query += """
            ORDER BY name
            LIMIT :limit OFFSET :offset
        """
        
        params["limit"] = limit
        params["offset"] = offset
        
        rows = await db.fetch_all(query, params)
        
        return [
            Artist(
                id=row["id"],
                name=row["name"],
                birth_year=row["birth_year"],
                death_year=row["death_year"],
                nationality=row["nationality"],
                movement=row["movement"],
                biography=row["biography"],
                verified=row["verified"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            for row in rows
        ]
    
    @staticmethod
    async def search_artists(
        db: Database,
        query_text: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Artist]:
        """Search artists by name with full-text search"""
        
        query = """
            SELECT 
                id, name, birth_year, death_year, nationality, movement,
                biography, verified, created_at, updated_at,
                ts_rank(
                    to_tsvector('english', name || ' ' || COALESCE(nationality, '')),
                    to_tsquery('english', :search_query)
                ) as rank
            FROM artists
            WHERE to_tsvector('english', name || ' ' || COALESCE(nationality, ''))
                  @@ to_tsquery('english', :search_query)
            ORDER BY rank DESC, name
            LIMIT :limit OFFSET :offset
        """
        
        # Prepare search query - simple word splitting for now
        search_terms = query_text.strip().split()
        search_query = " | ".join(term for term in search_terms if len(term) > 2)
        
        params = {
            "search_query": search_query,
            "limit": limit,
            "offset": offset
        }
        
        rows = await db.fetch_all(query, params)
        
        return [
            Artist(
                id=row["id"],
                name=row["name"],
                birth_year=row["birth_year"],
                death_year=row["death_year"],
                nationality=row["nationality"],
                movement=row["movement"],
                biography=row["biography"],
                verified=row["verified"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            for row in rows
        ]
    
    @staticmethod
    async def get_artist_by_id(db: Database, artist_id: int) -> Optional[Artist]:
        """Get artist by ID"""
        
        query = """
            SELECT 
                id, name, birth_year, death_year, nationality, movement,
                biography, verified, created_at, updated_at
            FROM artists
            WHERE id = :artist_id
        """
        
        row = await db.fetch_one(query, {"artist_id": artist_id})
        
        if not row:
            return None
            
        return Artist(
            id=row["id"],
            name=row["name"],
            birth_year=row["birth_year"],
            death_year=row["death_year"],
            nationality=row["nationality"],
            movement=row["movement"],
            biography=row["biography"],
            verified=row["verified"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
    
    @staticmethod
    async def get_artist_by_name(db: Database, name: str) -> Optional[Artist]:
        """Get artist by name (exact match)"""
        
        query = """
            SELECT 
                id, name, birth_year, death_year, nationality, movement,
                biography, verified, created_at, updated_at
            FROM artists
            WHERE LOWER(name) = LOWER(:name)
        """
        
        row = await db.fetch_one(query, {"name": name})
        
        if not row:
            return None
            
        return Artist(
            id=row["id"],
            name=row["name"],
            birth_year=row["birth_year"],
            death_year=row["death_year"],
            nationality=row["nationality"],
            movement=row["movement"],
            biography=row["biography"],
            verified=row["verified"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
    
    @staticmethod
    async def create_artist(db: Database, artist_data: ArtistCreate) -> Artist:
        """Create new artist"""
        
        query = """
            INSERT INTO artists (name, birth_year, death_year, nationality, movement, biography)
            VALUES (:name, :birth_year, :death_year, :nationality, :movement, :biography)
            RETURNING id, name, birth_year, death_year, nationality, movement,
                      biography, verified, created_at, updated_at
        """
        
        params = {
            "name": artist_data.name,
            "birth_year": artist_data.birth_year,
            "death_year": artist_data.death_year,
            "nationality": artist_data.nationality,
            "movement": artist_data.movement,
            "biography": artist_data.biography
        }
        
        row = await db.fetch_one(query, params)
        
        return Artist(
            id=row["id"],
            name=row["name"],
            birth_year=row["birth_year"],
            death_year=row["death_year"],
            nationality=row["nationality"],
            movement=row["movement"],
            biography=row["biography"],
            verified=row["verified"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
    
    @staticmethod
    async def find_or_create_artist(db: Database, name: str, **kwargs) -> Artist:
        """Find existing artist by name or create new one"""
        
        # Try to find existing artist
        existing_artist = await ArtistService.get_artist_by_name(db, name)
        if existing_artist:
            return existing_artist
        
        # Create new artist
        artist_data = ArtistCreate(
            name=name,
            birth_year=kwargs.get("birth_year"),
            death_year=kwargs.get("death_year"),
            nationality=kwargs.get("nationality"),
            movement=kwargs.get("movement"),
            biography=kwargs.get("biography")
        )
        
        return await ArtistService.create_artist(db, artist_data)
    
    @staticmethod
    async def get_artist_lots(
        db: Database,
        artist_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get lots by specific artist"""
        
        query = """
            SELECT 
                l.id, l.lot_number, l.title, l.estimated_price_min, 
                l.estimated_price_max, l.final_price, l.sold, l.currency,
                l.dimensions, l.medium, l.images,
                au.title as auction_title, au.start_date as auction_date,
                h.name as house_name
            FROM lots l
            JOIN auctions au ON l.auction_id = au.id
            JOIN auction_houses h ON au.house_id = h.id
            WHERE l.artist_id = :artist_id
            ORDER BY au.start_date DESC NULLS LAST, l.final_price DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """
        
        rows = await db.fetch_all(query, {
            "artist_id": artist_id,
            "limit": limit,
            "offset": offset
        })
        
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_artist_stats(db: Database, artist_id: int) -> Dict[str, Any]:
        """Get comprehensive statistics for artist"""
        
        # Basic stats
        basic_stats_query = """
            SELECT 
                COUNT(l.id) as total_lots,
                COUNT(l.id) FILTER (WHERE l.sold = true) as lots_sold,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_sale_price,
                MIN(l.final_price) FILTER (WHERE l.sold = true) as min_sale_price,
                MAX(l.final_price) FILTER (WHERE l.sold = true) as max_sale_price,
                COUNT(DISTINCT au.id) as total_auctions,
                COUNT(DISTINCT h.id) as auction_houses,
                MIN(au.start_date) as first_auction,
                MAX(au.start_date) as last_auction
            FROM lots l
            JOIN auctions au ON l.auction_id = au.id
            JOIN auction_houses h ON au.house_id = h.id
            WHERE l.artist_id = :artist_id
        """
        
        basic_stats = await db.fetch_one(basic_stats_query, {"artist_id": artist_id})
        
        # Price trends (last 24 months)
        price_trends_query = """
            SELECT 
                DATE_TRUNC('month', au.start_date) as month,
                COUNT(l.id) FILTER (WHERE l.sold = true) as lots_sold,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_price,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales
            FROM lots l
            JOIN auctions au ON l.auction_id = au.id
            WHERE l.artist_id = :artist_id
            AND au.start_date >= NOW() - INTERVAL '24 months'
            AND l.sold = true
            GROUP BY DATE_TRUNC('month', au.start_date)
            ORDER BY month
        """
        
        price_trends = await db.fetch_all(price_trends_query, {"artist_id": artist_id})
        
        # Top sales
        top_sales_query = """
            SELECT 
                l.id, l.title, l.final_price, l.currency, l.dimensions,
                au.title as auction_title, au.start_date,
                h.name as house_name
            FROM lots l
            JOIN auctions au ON l.auction_id = au.id
            JOIN auction_houses h ON au.house_id = h.id
            WHERE l.artist_id = :artist_id AND l.sold = true
            ORDER BY l.final_price DESC
            LIMIT 10
        """
        
        top_sales = await db.fetch_all(top_sales_query, {"artist_id": artist_id})
        
        # Medium analysis
        medium_stats_query = """
            SELECT 
                l.medium,
                COUNT(l.id) as lot_count,
                COUNT(l.id) FILTER (WHERE l.sold = true) as sold_count,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_price,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales
            FROM lots l
            JOIN auctions au ON l.auction_id = au.id
            WHERE l.artist_id = :artist_id
            AND l.medium IS NOT NULL
            GROUP BY l.medium
            ORDER BY total_sales DESC NULLS LAST
        """
        
        medium_stats = await db.fetch_all(medium_stats_query, {"artist_id": artist_id})
        
        # Auction house performance
        house_performance_query = """
            SELECT 
                h.name as house_name,
                COUNT(l.id) as total_lots,
                COUNT(l.id) FILTER (WHERE l.sold = true) as sold_lots,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_price
            FROM lots l
            JOIN auctions au ON l.auction_id = au.id
            JOIN auction_houses h ON au.house_id = h.id
            WHERE l.artist_id = :artist_id
            GROUP BY h.id, h.name
            HAVING COUNT(l.id) > 0
            ORDER BY total_sales DESC NULLS LAST
        """
        
        house_performance = await db.fetch_all(house_performance_query, {"artist_id": artist_id})
        
        return {
            "basic_stats": dict(basic_stats) if basic_stats else {},
            "price_trends": [dict(row) for row in price_trends],
            "top_sales": [dict(row) for row in top_sales],
            "medium_stats": [dict(row) for row in medium_stats],
            "house_performance": [dict(row) for row in house_performance],
            "sale_rate": (
                (basic_stats["lots_sold"] / basic_stats["total_lots"] * 100) 
                if basic_stats and basic_stats["total_lots"] and basic_stats["total_lots"] > 0 
                else 0
            ),
            "market_presence": {
                "years_active": ArtistService._calculate_years_active(basic_stats),
                "auction_frequency": ArtistService._calculate_auction_frequency(basic_stats)
            }
        }
    
    @staticmethod
    def _calculate_years_active(basic_stats: Dict[str, Any]) -> Optional[int]:
        """Calculate years between first and last auction"""
        if not basic_stats or not basic_stats.get("first_auction") or not basic_stats.get("last_auction"):
            return None
            
        first = basic_stats["first_auction"]
        last = basic_stats["last_auction"]
        
        return (last - first).days // 365 if (last - first).days > 365 else 1
    
    @staticmethod
    def _calculate_auction_frequency(basic_stats: Dict[str, Any]) -> Optional[float]:
        """Calculate average auctions per year"""
        if not basic_stats or not basic_stats.get("total_auctions"):
            return None
            
        years_active = ArtistService._calculate_years_active(basic_stats)
        if not years_active:
            return None
            
        return basic_stats["total_auctions"] / years_active
    
    @staticmethod
    async def get_trending_artists(
        db: Database,
        period_days: int = 90,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get trending artists based on recent sales activity"""
        
        query = """
            SELECT 
                a.id, a.name, a.nationality, a.movement,
                COUNT(l.id) FILTER (WHERE l.sold = true) as recent_sales,
                SUM(l.final_price) FILTER (WHERE l.sold = true) as total_sales,
                AVG(l.final_price) FILTER (WHERE l.sold = true) as avg_price,
                COUNT(DISTINCT au.id) as auction_count
            FROM artists a
            JOIN lots l ON a.id = l.artist_id
            JOIN auctions au ON l.auction_id = au.id
            WHERE au.start_date >= NOW() - INTERVAL '%d days'
            AND l.sold = true
            GROUP BY a.id, a.name, a.nationality, a.movement
            HAVING COUNT(l.id) FILTER (WHERE l.sold = true) >= 2
            ORDER BY total_sales DESC, recent_sales DESC
            LIMIT :limit
        """ % period_days
        
        rows = await db.fetch_all(query, {"limit": limit})
        
        return [dict(row) for row in rows]
    
    @staticmethod
    async def verify_artist(db: Database, artist_id: int) -> bool:
        """Mark artist as verified"""
        
        query = """
            UPDATE artists 
            SET verified = true, updated_at = NOW()
            WHERE id = :artist_id
        """
        
        result = await db.execute(query, {"artist_id": artist_id})
        return result > 0