#!/usr/bin/env python3
"""
Populate the auction houses database with consistent test data that matches the current schema.
This script creates:
- Real auction houses using only fields that exist in the schema
- Sample auctions with realistic dates and descriptions
- Art lots with artists, categories, and pricing

Usage: python scripts/populate_consistent_test_data.py
"""

import asyncio
import asyncpg
import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any
import json

# Database connection details
DATABASE_URL = "postgresql://auction_user:auction_pass@localhost:5432/auction_houses"

# Test data for auction houses (using only existing schema fields)
AUCTION_HOUSES = [
    {
        "name": "Christie's",
        "country": "Reino Unido",
        "website": "https://www.christies.com",
        "description": "Founded in 1766 by James Christie, Christie's is a world-leading art and luxury business.",
        "scraping_config": {
            "strategy": "html_static",
            "frequency": "daily",
            "urls": {
                "upcoming": "https://www.christies.com/auctions/upcoming",
                "current": "https://www.christies.com/auctions/current"
            }
        }
    },
    {
        "name": "Sotheby's",
        "country": "Reino Unido", 
        "website": "https://www.sothebys.com",
        "description": "Founded in 1744, Sotheby's is the world's premier destination for art and luxury.",
        "scraping_config": {
            "strategy": "html_static",
            "frequency": "daily",
            "urls": {
                "upcoming": "https://www.sothebys.com/en/auctions/upcoming",
                "current": "https://www.sothebys.com/en/auctions/current"
            }
        }
    },
    {
        "name": "Durán Arte y Subastas",
        "country": "España",
        "website": "https://www.duran-subastas.com",
        "description": "Casa de subastas española fundada en 1969, especializada en arte español y europeo.",
        "scraping_config": {
            "strategy": "html_static",
            "frequency": "weekly",
            "urls": {
                "current": "https://www.duran-subastas.com/subasta-647-julio-2025"
            }
        }
    },
    {
        "name": "Morton Subastas",
        "country": "México",
        "website": "https://www.mortonsubastas.com",
        "description": "Casa de subastas mexicana líder en arte latinoamericano y mexicano.",
        "scraping_config": {
            "strategy": "html_static",
            "frequency": "weekly",
            "urls": {
                "current": "https://live.mortonsubastas.com/en/auctions"
            }
        }
    },
    {
        "name": "Setdart",
        "country": "España",
        "website": "https://www.setdart.com",
        "description": "Casa de subastas especializada en arte contemporáneo y subastas online.",
        "scraping_config": {
            "strategy": "html_ajax",
            "frequency": "daily",
            "urls": {
                "calendar": "https://www.setdart.com/es/subastas/calendario"
            }
        }
    },
    {
        "name": "Bogotá Auctions",
        "country": "Colombia",
        "website": "https://www.bogotaauctions.com",
        "description": "Casa de subastas colombiana especializada en arte latinoamericano.",
        "scraping_config": {
            "strategy": "html_static",
            "frequency": "daily",
            "urls": {
                "active": "https://www.bogotaauctions.com/es/subastas-activas",
                "historical": "https://www.bogotaauctions.com/es/subastas-historicas"
            }
        }
    }
]

# Sample artists data
ARTISTS = [
    {"name": "Fernando Botero", "birth_year": 1932, "death_year": None, "nationality": "Colombiano"},
    {"name": "Pablo Picasso", "birth_year": 1881, "death_year": 1973, "nationality": "Español"},
    {"name": "Diego Rivera", "birth_year": 1886, "death_year": 1957, "nationality": "Mexicano"},
    {"name": "Frida Kahlo", "birth_year": 1907, "death_year": 1954, "nationality": "Mexicana"},
    {"name": "Salvador Dalí", "birth_year": 1904, "death_year": 1989, "nationality": "Español"},
    {"name": "Joan Miró", "birth_year": 1893, "death_year": 1983, "nationality": "Español"},
    {"name": "Eduardo Chillida", "birth_year": 1924, "death_year": 2002, "nationality": "Español"},
    {"name": "Antonio López García", "birth_year": 1936, "death_year": None, "nationality": "Español"},
    {"name": "Beatriz Milhazes", "birth_year": 1960, "death_year": None, "nationality": "Brasileña"},
    {"name": "Gerhard Richter", "birth_year": 1932, "death_year": None, "nationality": "Alemán"},
    {"name": "David Hockney", "birth_year": 1937, "death_year": None, "nationality": "Británico"},
    {"name": "Banksy", "birth_year": None, "death_year": None, "nationality": "Británico"},
]

# Sample categories (hierarchical)
CATEGORIES = [
    {"name": "Pintura", "parent_category_id": None, "level": 0},
    {"name": "Escultura", "parent_category_id": None, "level": 0},
    {"name": "Fotografía", "parent_category_id": None, "level": 0},
    {"name": "Arte Gráfico", "parent_category_id": None, "level": 0},
    {"name": "Antigüedades", "parent_category_id": None, "level": 0},
    {"name": "Joyería", "parent_category_id": None, "level": 0},
    # Subcategories for painting
    {"name": "Óleo sobre lienzo", "parent_category_id": 1, "level": 1},
    {"name": "Acuarela", "parent_category_id": 1, "level": 1},
    {"name": "Arte Contemporáneo", "parent_category_id": 1, "level": 1},
    {"name": "Impresionismo", "parent_category_id": 1, "level": 1},
]

async def create_test_data():
    """Create comprehensive test data for the auction houses application"""
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        print("Creating auction houses...")
        house_ids = await create_auction_houses(conn)
        
        print("Creating artists...")
        artist_ids = await create_artists(conn)
        
        print("Creating categories...")
        category_ids = await create_categories(conn)
        
        print("Creating auctions...")
        auction_ids = await create_auctions(conn, house_ids)
        
        print("Creating lots...")
        await create_lots(conn, auction_ids, artist_ids, category_ids)
        
        print("Test data creation completed successfully!")
        
        # Print summary
        await print_summary(conn)
        
    except Exception as e:
        print(f"Error creating test data: {e}")
        raise
    finally:
        await conn.close()

async def create_auction_houses(conn: asyncpg.Connection) -> List[int]:
    """Create auction houses with proper schema fields"""
    house_ids = []
    
    for house in AUCTION_HOUSES:
        result = await conn.fetchrow("""
            INSERT INTO auction_houses (
                name, country, website, description, scraping_config, status
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (name, country) DO UPDATE SET
                website = EXCLUDED.website,
                description = EXCLUDED.description,
                scraping_config = EXCLUDED.scraping_config
            RETURNING id
        """, 
        house["name"], house["country"], house["website"],
        house["description"], json.dumps(house["scraping_config"]), "active")
        
        house_ids.append(result["id"])
    
    print(f"   Created {len(house_ids)} auction houses")
    return house_ids

async def create_artists(conn: asyncpg.Connection) -> List[int]:
    """Create artist records"""
    artist_ids = []
    
    for artist in ARTISTS:
        # Check if artist exists first
        existing = await conn.fetchrow("SELECT id FROM artists WHERE name = $1", artist["name"])
        if existing:
            artist_ids.append(existing["id"])
        else:
            result = await conn.fetchrow("""
                INSERT INTO artists (name, birth_year, death_year, nationality)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """,
            artist["name"], artist["birth_year"], artist["death_year"], artist["nationality"])
            
            artist_ids.append(result["id"])
    
    print(f"   Created {len(artist_ids)} artists")
    return artist_ids

async def create_categories(conn: asyncpg.Connection) -> List[int]:
    """Create hierarchical categories"""
    category_ids = []
    
    # First create parent categories
    for category in CATEGORIES:
        if category["parent_category_id"] is None:
            result = await conn.fetchrow("""
                INSERT INTO categories (name, parent_category_id, level)
                VALUES ($1, $2, $3)
                ON CONFLICT (name, parent_category_id) DO UPDATE SET
                    level = EXCLUDED.level
                RETURNING id
            """,
            category["name"], None, category["level"])
            
            category_ids.append(result["id"])
    
    # Then create subcategories with proper parent_id references
    for category in CATEGORIES:
        if category["parent_category_id"] is not None:
            parent_id = category_ids[category["parent_category_id"] - 1]  # Adjust for 0-based indexing
            
            result = await conn.fetchrow("""
                INSERT INTO categories (name, parent_category_id, level)
                VALUES ($1, $2, $3)
                ON CONFLICT (name, parent_category_id) DO UPDATE SET
                    level = EXCLUDED.level
                RETURNING id
            """,
            category["name"], parent_id, category["level"])
            
            category_ids.append(result["id"])
    
    print(f"   Created {len(category_ids)} categories")
    return category_ids

async def create_auctions(conn: asyncpg.Connection, house_ids: List[int]) -> List[int]:
    """Create sample auctions with various statuses"""
    auction_ids = []
    
    # Auction templates
    auction_templates = [
        {
            "title": "Arte Contemporáneo - Subasta de Primavera",
            "description": "Excepcional selección de obras de arte contemporáneo de artistas internacionales.",
            "auction_type": "live",
            "location": "Madrid",
            "currency": "EUR"
        },
        {
            "title": "Maestros del Siglo XX",
            "description": "Importantes obras de los grandes maestros del arte moderno.",
            "auction_type": "hybrid",
            "location": "Barcelona",
            "currency": "EUR"
        },
        {
            "title": "Arte Latinoamericano",
            "description": "Colección excepcional de arte latinoamericano contemporáneo y moderno.",
            "auction_type": "online",
            "location": "Buenos Aires",
            "currency": "USD"
        },
        {
            "title": "Pintura Española del Siglo XIX",
            "description": "Selección de obras representativas de la pintura española decimonónica.",
            "auction_type": "live",
            "location": "Sevilla",
            "currency": "EUR"
        },
        {
            "title": "Arte Contemporáneo Internacional",
            "description": "Obras de artistas contemporáneos de reconocimiento mundial.",
            "auction_type": "hybrid",
            "location": "Ciudad de México",
            "currency": "USD"
        }
    ]
    
    statuses = ["upcoming", "active", "completed"]
    
    for i in range(15):  # Create 15 auctions
        template = random.choice(auction_templates)
        house_id = random.choice(house_ids)
        status = random.choice(statuses)
        
        # Generate dates based on status
        if status == "upcoming":
            start_date = datetime.now() + timedelta(days=random.randint(7, 60))
            end_date = start_date + timedelta(hours=random.randint(2, 8))
        elif status == "active":
            start_date = datetime.now() - timedelta(hours=random.randint(1, 24))
            end_date = datetime.now() + timedelta(hours=random.randint(1, 12))
        else:  # completed
            start_date = datetime.now() - timedelta(days=random.randint(7, 180))
            end_date = start_date + timedelta(hours=random.randint(2, 8))
        
        title = f"{template['title']} #{i+1}"
        
        result = await conn.fetchrow("""
            INSERT INTO auctions (
                house_id, title, description, start_date, end_date,
                status, location, auction_type, currency, slug
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
        """,
        house_id, title, template["description"], start_date, end_date,
        status, template["location"], template["auction_type"], 
        template["currency"], f"auction-{i+1}")
        
        auction_ids.append(result["id"])
    
    print(f"   Created {len(auction_ids)} auctions")
    return auction_ids

async def create_lots(conn: asyncpg.Connection, auction_ids: List[int], 
                     artist_ids: List[int], category_ids: List[int]):
    """Create lots for auctions"""
    lot_count = 0
    
    # Lot templates
    lot_templates = [
        {"title": "Sin título", "medium": "Óleo sobre lienzo", "dimensions": "100 x 80 cm"},
        {"title": "Paisaje urbano", "medium": "Acrílico sobre lienzo", "dimensions": "120 x 90 cm"},
        {"title": "Retrato", "medium": "Óleo sobre tabla", "dimensions": "60 x 50 cm"},
        {"title": "Naturaleza muerta", "medium": "Óleo sobre lienzo", "dimensions": "80 x 60 cm"},
        {"title": "Abstracción", "medium": "Técnica mixta sobre papel", "dimensions": "50 x 70 cm"},
        {"title": "Composición", "medium": "Acuarela sobre papel", "dimensions": "40 x 30 cm"},
    ]
    
    for auction_id in auction_ids:
        # Each auction has between 5-25 lots
        num_lots = random.randint(5, 25)
        
        for lot_num in range(1, num_lots + 1):
            template = random.choice(lot_templates)
            artist_id = random.choice(artist_ids) if random.random() > 0.1 else None  # 90% have artists
            category_id = random.choice(category_ids)
            
            # Generate realistic prices in different ranges
            price_ranges = [
                (500, 2000),      # Affordable range
                (2000, 10000),    # Mid range
                (10000, 50000),   # High range
                (50000, 200000),  # Premium range
            ]
            price_range = random.choice(price_ranges)
            estimate_min = Decimal(str(random.randint(price_range[0], price_range[1])))
            estimate_max = estimate_min * Decimal(str(random.uniform(1.2, 2.0)))
            
            # Some lots are sold with final prices
            sold = random.random() > 0.3  # 70% sold rate
            final_price = None
            if sold:
                # Final price usually within or slightly above estimate
                multiplier = random.uniform(0.8, 1.5)  # Can go below or above estimate
                final_price = estimate_min * Decimal(str(multiplier))
            
            title = f"{template['title']} #{lot_num}"
            if artist_id:
                artist_name = await conn.fetchval("SELECT name FROM artists WHERE id = $1", artist_id)
                title = f"{artist_name} - {title}"
            
            await conn.execute("""
                INSERT INTO lots (
                    auction_id, artist_id, category_id, lot_number, title, 
                    description, medium, dimensions, estimated_price_min, 
                    estimated_price_max, final_price, sold, currency
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            auction_id, artist_id, category_id, str(lot_num), title,
            f"Obra de {template['medium'].lower()} de excelente calidad y conservación.",
            template["medium"], template["dimensions"], estimate_min, estimate_max,
            final_price, sold, "EUR")
            
            lot_count += 1
    
    print(f"   Created {lot_count} lots")

async def print_summary(conn: asyncpg.Connection):
    """Print a summary of created data"""
    print("\nDATABASE SUMMARY:")
    
    houses_count = await conn.fetchval("SELECT COUNT(*) FROM auction_houses")
    print(f"   Auction Houses: {houses_count}")
    
    artists_count = await conn.fetchval("SELECT COUNT(*) FROM artists")
    print(f"   Artists: {artists_count}")
    
    categories_count = await conn.fetchval("SELECT COUNT(*) FROM categories")
    print(f"   Categories: {categories_count}")
    
    auctions_count = await conn.fetchval("SELECT COUNT(*) FROM auctions")
    print(f"   Auctions: {auctions_count}")
    
    lots_count = await conn.fetchval("SELECT COUNT(*) FROM lots")
    print(f"   Lots: {lots_count}")
    
    # Status breakdown
    print(f"\nAUCTION STATUS BREAKDOWN:")
    status_counts = await conn.fetch("""
        SELECT status, COUNT(*) as count 
        FROM auctions 
        GROUP BY status 
        ORDER BY count DESC
    """)
    for row in status_counts:
        print(f"   {row['status']}: {row['count']}")
    
    # Recent lots value
    total_value = await conn.fetchval("""
        SELECT SUM(final_price) 
        FROM lots 
        WHERE sold = true AND final_price IS NOT NULL
    """)
    if total_value:
        print(f"\nTotal Sales Value: EUR{total_value:,.2f}")

if __name__ == "__main__":
    print("Populating auction houses database with test data...")
    asyncio.run(create_test_data())