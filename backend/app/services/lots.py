from typing import List, Optional, Dict, Any
from databases import Database
from decimal import Decimal

from app.models.schemas import Lot, LotCreate, LotUpdate, LotFilters

class LotService:
    """Service layer for lots business logic"""
    
    @staticmethod
    async def get_lots(
        db: Database,
        filters: LotFilters,
        limit: int = 50,
        offset: int = 0
    ) -> List[Lot]:
        """Get lots with optional filters"""
        
        query = """
            SELECT 
                l.id, l.auction_id, l.lot_number, l.title, l.description,
                l.artist_id, l.category_id, l.estimated_price_min, l.estimated_price_max,
                l.final_price, l.hammer_price, l.buyers_premium, l.currency, l.sold,
                l.images, l.dimensions, l.medium, l.provenance, l.condition_report,
                l.signature, l.external_id, l.external_url, l.created_at, l.updated_at,
                a.name as artist_name,
                c.name as category_name,
                au.title as auction_title,
                h.name as house_name
            FROM lots l
            LEFT JOIN artists a ON l.artist_id = a.id
            LEFT JOIN categories c ON l.category_id = c.id
            LEFT JOIN auctions au ON l.auction_id = au.id
            LEFT JOIN auction_houses h ON au.house_id = h.id
            WHERE 1=1
        """
        
        params = {}
        
        if filters.auction_id:
            query += " AND l.auction_id = :auction_id"
            params["auction_id"] = filters.auction_id
            
        if filters.artist_id:
            query += " AND l.artist_id = :artist_id"
            params["artist_id"] = filters.artist_id
            
        if filters.category_id:
            query += " AND l.category_id = :category_id"
            params["category_id"] = filters.category_id
            
        if filters.house_id:
            query += " AND au.house_id = :house_id"
            params["house_id"] = filters.house_id
            
        if filters.sold is not None:
            query += " AND l.sold = :sold"
            params["sold"] = filters.sold
            
        if filters.price_min:
            query += " AND l.final_price >= :price_min"
            params["price_min"] = filters.price_min
            
        if filters.price_max:
            query += " AND l.final_price <= :price_max"
            params["price_max"] = filters.price_max
            
        if filters.currency:
            query += " AND l.currency = :currency"
            params["currency"] = filters.currency
        
        query += """
            ORDER BY l.created_at DESC
            LIMIT :limit OFFSET :offset
        """
        
        params["limit"] = limit
        params["offset"] = offset
        
        rows = await db.fetch_all(query, params)
        
        return [LotService._row_to_lot(row) for row in rows]
    
    @staticmethod
    async def search_lots(
        db: Database,
        search_params: Dict[str, Any]
    ) -> List[Lot]:
        """Search lots with full-text search and filters"""
        
        query = """
            SELECT 
                l.id, l.auction_id, l.lot_number, l.title, l.description,
                l.artist_id, l.category_id, l.estimated_price_min, l.estimated_price_max,
                l.final_price, l.hammer_price, l.buyers_premium, l.currency, l.sold,
                l.images, l.dimensions, l.medium, l.provenance, l.condition_report,
                l.signature, l.external_id, l.external_url, l.created_at, l.updated_at,
                a.name as artist_name,
                c.name as category_name,
                au.title as auction_title,
                h.name as house_name,
                ts_rank(
                    to_tsvector('english', l.title || ' ' || COALESCE(l.description, '')),
                    to_tsquery('english', :search_query)
                ) as rank
            FROM lots l
            LEFT JOIN artists a ON l.artist_id = a.id
            LEFT JOIN categories c ON l.category_id = c.id
            LEFT JOIN auctions au ON l.auction_id = au.id
            LEFT JOIN auction_houses h ON au.house_id = h.id
            WHERE to_tsvector('english', l.title || ' ' || COALESCE(l.description, ''))
                  @@ to_tsquery('english', :search_query)
        """
        
        params = {
            "search_query": LotService._prepare_search_query(search_params["q"]),
            "limit": search_params.get("limit", 50),
            "offset": search_params.get("offset", 0)
        }
        
        # Additional filters
        if search_params.get("artist"):
            query += " AND a.name ILIKE :artist_filter"
            params["artist_filter"] = f"%{search_params['artist']}%"
            
        if search_params.get("category"):
            query += " AND c.name ILIKE :category_filter"
            params["category_filter"] = f"%{search_params['category']}%"
            
        if search_params.get("house"):
            query += " AND h.name ILIKE :house_filter"
            params["house_filter"] = f"%{search_params['house']}%"
            
        if search_params.get("price_min"):
            query += " AND l.final_price >= :price_min"
            params["price_min"] = search_params["price_min"]
            
        if search_params.get("price_max"):
            query += " AND l.final_price <= :price_max"
            params["price_max"] = search_params["price_max"]
        
        query += """
            ORDER BY rank DESC, l.final_price DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """
        
        rows = await db.fetch_all(query, params)
        
        return [LotService._row_to_lot(row) for row in rows]
    
    @staticmethod
    def _prepare_search_query(query: str) -> str:
        """Prepare search query for PostgreSQL full-text search"""
        # Basic cleanup and preparation
        # Remove special characters, split words, add OR operators
        words = query.strip().split()
        # For now, simple OR search - can be enhanced later
        return " | ".join(word for word in words if len(word) > 2)
    
    @staticmethod
    async def get_lot_by_id(db: Database, lot_id: int) -> Optional[Lot]:
        """Get lot by ID with all related information"""
        
        query = """
            SELECT 
                l.id, l.auction_id, l.lot_number, l.title, l.description,
                l.artist_id, l.category_id, l.estimated_price_min, l.estimated_price_max,
                l.final_price, l.hammer_price, l.buyers_premium, l.currency, l.sold,
                l.images, l.dimensions, l.medium, l.provenance, l.condition_report,
                l.signature, l.external_id, l.external_url, l.created_at, l.updated_at,
                a.name as artist_name,
                c.name as category_name,
                au.title as auction_title,
                h.name as house_name
            FROM lots l
            LEFT JOIN artists a ON l.artist_id = a.id
            LEFT JOIN categories c ON l.category_id = c.id
            LEFT JOIN auctions au ON l.auction_id = au.id
            LEFT JOIN auction_houses h ON au.house_id = h.id
            WHERE l.id = :lot_id
        """
        
        row = await db.fetch_one(query, {"lot_id": lot_id})
        
        if not row:
            return None
            
        return LotService._row_to_lot(row)
    
    @staticmethod
    async def create_lot(db: Database, lot_data: LotCreate) -> Lot:
        """Create new lot"""
        
        query = """
            INSERT INTO lots (
                auction_id, lot_number, title, description, artist_id, category_id,
                estimated_price_min, estimated_price_max, dimensions, medium,
                provenance, condition_report, signature, external_id, external_url, currency
            )
            VALUES (
                :auction_id, :lot_number, :title, :description, :artist_id, :category_id,
                :estimated_price_min, :estimated_price_max, :dimensions, :medium,
                :provenance, :condition_report, :signature, :external_id, :external_url, :currency
            )
            RETURNING id, auction_id, lot_number, title, description, artist_id, category_id,
                      estimated_price_min, estimated_price_max, final_price, hammer_price,
                      buyers_premium, currency, sold, images, dimensions, medium, provenance,
                      condition_report, signature, external_id, external_url, created_at, updated_at
        """
        
        params = {
            "auction_id": lot_data.auction_id,
            "lot_number": lot_data.lot_number,
            "title": lot_data.title,
            "description": lot_data.description,
            "artist_id": lot_data.artist_id,
            "category_id": lot_data.category_id,
            "estimated_price_min": lot_data.estimated_price_min,
            "estimated_price_max": lot_data.estimated_price_max,
            "dimensions": lot_data.dimensions,
            "medium": lot_data.medium,
            "provenance": lot_data.provenance,
            "condition_report": lot_data.condition_report,
            "signature": lot_data.signature,
            "external_id": lot_data.external_id,
            "external_url": str(lot_data.external_url) if lot_data.external_url else None,
            "currency": lot_data.currency
        }
        
        row = await db.fetch_one(query, params)
        
        return LotService._row_to_lot(row, include_relations=False)
    
    @staticmethod
    async def update_lot(
        db: Database,
        lot_id: int,
        lot_data: LotUpdate
    ) -> Optional[Lot]:
        """Update lot"""
        
        # Build dynamic update query
        set_clauses = []
        params = {"lot_id": lot_id}
        
        if lot_data.title is not None:
            set_clauses.append("title = :title")
            params["title"] = lot_data.title
            
        if lot_data.description is not None:
            set_clauses.append("description = :description")
            params["description"] = lot_data.description
            
        if lot_data.final_price is not None:
            set_clauses.append("final_price = :final_price")
            params["final_price"] = lot_data.final_price
            
        if lot_data.hammer_price is not None:
            set_clauses.append("hammer_price = :hammer_price")
            params["hammer_price"] = lot_data.hammer_price
            
        if lot_data.buyers_premium is not None:
            set_clauses.append("buyers_premium = :buyers_premium")
            params["buyers_premium"] = lot_data.buyers_premium
            
        if lot_data.sold is not None:
            set_clauses.append("sold = :sold")
            params["sold"] = lot_data.sold
        
        if not set_clauses:
            return await LotService.get_lot_by_id(db, lot_id)
        
        query = f"""
            UPDATE lots 
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = :lot_id
        """
        
        result = await db.execute(query, params)
        
        if result == 0:
            return None
            
        return await LotService.get_lot_by_id(db, lot_id)
    
    @staticmethod
    async def delete_lot(db: Database, lot_id: int) -> bool:
        """Delete lot"""
        
        query = "DELETE FROM lots WHERE id = :lot_id"
        
        result = await db.execute(query, {"lot_id": lot_id})
        return result > 0
    
    @staticmethod
    async def get_similar_lots(
        db: Database,
        lot_id: int,
        limit: int = 10
    ) -> List[Lot]:
        """Get lots similar to the specified lot"""
        
        # First get the reference lot
        ref_lot = await LotService.get_lot_by_id(db, lot_id)
        if not ref_lot:
            return []
        
        # Find similar lots based on artist, category, and price range
        query = """
            SELECT 
                l.id, l.auction_id, l.lot_number, l.title, l.description,
                l.artist_id, l.category_id, l.estimated_price_min, l.estimated_price_max,
                l.final_price, l.hammer_price, l.buyers_premium, l.currency, l.sold,
                l.images, l.dimensions, l.medium, l.provenance, l.condition_report,
                l.signature, l.external_id, l.external_url, l.created_at, l.updated_at,
                a.name as artist_name,
                c.name as category_name,
                au.title as auction_title,
                h.name as house_name,
                (
                    CASE WHEN l.artist_id = :artist_id THEN 3 ELSE 0 END +
                    CASE WHEN l.category_id = :category_id THEN 2 ELSE 0 END +
                    CASE WHEN l.final_price BETWEEN :price_min AND :price_max THEN 1 ELSE 0 END
                ) as similarity_score
            FROM lots l
            LEFT JOIN artists a ON l.artist_id = a.id
            LEFT JOIN categories c ON l.category_id = c.id
            LEFT JOIN auctions au ON l.auction_id = au.id
            LEFT JOIN auction_houses h ON au.house_id = h.id
            WHERE l.id != :lot_id
            AND (
                l.artist_id = :artist_id OR
                l.category_id = :category_id OR
                (l.final_price IS NOT NULL AND l.final_price BETWEEN :price_min AND :price_max)
            )
            ORDER BY similarity_score DESC, l.final_price DESC NULLS LAST
            LIMIT :limit
        """
        
        # Define price range for similarity (±50% of reference lot price)
        ref_price = ref_lot.final_price or ref_lot.estimated_price_max or ref_lot.estimated_price_min or Decimal(1000)
        price_min = ref_price * Decimal(0.5)
        price_max = ref_price * Decimal(1.5)
        
        params = {
            "lot_id": lot_id,
            "artist_id": ref_lot.artist_id,
            "category_id": ref_lot.category_id,
            "price_min": price_min,
            "price_max": price_max,
            "limit": limit
        }
        
        rows = await db.fetch_all(query, params)
        
        return [LotService._row_to_lot(row) for row in rows]
    
    @staticmethod
    async def get_recent_lots(
        db: Database,
        limit: int = 50,
        offset: int = 0,
        days: int = 30
    ) -> List[Lot]:
        """Get recently added/sold lots"""
        
        query = """
            SELECT 
                l.id, l.auction_id, l.lot_number, l.title, l.description,
                l.artist_id, l.category_id, l.estimated_price_min, l.estimated_price_max,
                l.final_price, l.hammer_price, l.buyers_premium, l.currency, l.sold,
                l.images, l.dimensions, l.medium, l.provenance, l.condition_report,
                l.signature, l.external_id, l.external_url, l.created_at, l.updated_at,
                a.name as artist_name,
                c.name as category_name,
                au.title as auction_title,
                h.name as house_name
            FROM lots l
            LEFT JOIN artists a ON l.artist_id = a.id
            LEFT JOIN categories c ON l.category_id = c.id
            LEFT JOIN auctions au ON l.auction_id = au.id
            LEFT JOIN auction_houses h ON au.house_id = h.id
            WHERE l.created_at >= NOW() - INTERVAL '%d days'
            ORDER BY l.created_at DESC
            LIMIT :limit OFFSET :offset
        """ % days
        
        rows = await db.fetch_all(query, {"limit": limit, "offset": offset})
        
        return [LotService._row_to_lot(row) for row in rows]
    
    @staticmethod
    async def get_high_value_lots(
        db: Database,
        min_value: Decimal = Decimal(10000),
        limit: int = 50
    ) -> List[Lot]:
        """Get high-value lots (sold above specified amount)"""
        
        query = """
            SELECT 
                l.id, l.auction_id, l.lot_number, l.title, l.description,
                l.artist_id, l.category_id, l.estimated_price_min, l.estimated_price_max,
                l.final_price, l.hammer_price, l.buyers_premium, l.currency, l.sold,
                l.images, l.dimensions, l.medium, l.provenance, l.condition_report,
                l.signature, l.external_id, l.external_url, l.created_at, l.updated_at,
                a.name as artist_name,
                c.name as category_name,
                au.title as auction_title,
                h.name as house_name
            FROM lots l
            LEFT JOIN artists a ON l.artist_id = a.id
            LEFT JOIN categories c ON l.category_id = c.id
            LEFT JOIN auctions au ON l.auction_id = au.id
            LEFT JOIN auction_houses h ON au.house_id = h.id
            WHERE l.sold = true AND l.final_price >= :min_value
            ORDER BY l.final_price DESC
            LIMIT :limit
        """
        
        rows = await db.fetch_all(query, {"min_value": min_value, "limit": limit})
        
        return [LotService._row_to_lot(row) for row in rows]
    
    @staticmethod
    def _row_to_lot(row, include_relations: bool = True) -> Lot:
        """Convert database row to Lot object"""
        
        return Lot(
            id=row["id"],
            auction_id=row["auction_id"],
            lot_number=row["lot_number"],
            title=row["title"],
            description=row["description"],
            artist_id=row["artist_id"],
            category_id=row["category_id"],
            estimated_price_min=row["estimated_price_min"],
            estimated_price_max=row["estimated_price_max"],
            final_price=row["final_price"],
            hammer_price=row["hammer_price"],
            buyers_premium=row["buyers_premium"],
            currency=row["currency"],
            sold=row["sold"],
            images=row["images"] or [],
            dimensions=row["dimensions"],
            medium=row["medium"],
            provenance=row["provenance"],
            condition_report=row["condition_report"],
            signature=row["signature"],
            external_id=row["external_id"],
            external_url=row["external_url"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            # Related fields (if available)
            artist_name=row.get("artist_name") if include_relations else None,
            category_name=row.get("category_name") if include_relations else None,
            auction_title=row.get("auction_title") if include_relations else None,
            house_name=row.get("house_name") if include_relations else None
        )