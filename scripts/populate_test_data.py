#!/usr/bin/env python3
"""
Populate the auction houses database with realistic test data.
This script creates:
- Real auction houses (Christie's, Sotheby's, Durán, etc.)
- Sample auctions with realistic dates and descriptions
- Art lots with artists, categories, and pricing
- Artist information with biographies

Usage: python scripts/populate_test_data.py
"""

import asyncio
import asyncpg
import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any

# Database connection details
DATABASE_URL = "postgresql://auction_user:auction_pass@localhost:5432/auction_houses"

# Test data for auction houses
AUCTION_HOUSES = [
    {
        "name": "Christie's",
        "country": "United Kingdom", 
        "city": "London",
        "website": "https://www.christies.com",
        "description": "Founded in 1766 by James Christie, Christie's is a world-leading art and luxury business.",
        "specialties": ["Modern Art", "Impressionist Art", "Contemporary Art", "Jewelry", "Wine"],
        "established_year": 1766,
        "logo_url": "https://www.christies.com/img/christie_logo.png",
        "verified": True,
        "active": True
    },
    {
        "name": "Sotheby's", 
        "country": "United Kingdom",
        "city": "London", 
        "website": "https://www.sothebys.com",
        "description": "Founded in 1744, Sotheby's is the world's premier destination for art and luxury.",
        "specialties": ["Fine Art", "Jewelry", "Watches", "Wine", "Real Estate"],
        "established_year": 1744,
        "logo_url": "https://www.sothebys.com/content/dam/sothebys/logos/sothebys-logo.png",
        "verified": True,
        "active": True
    },
    {
        "name": "Durán Subastas",
        "country": "España",
        "city": "Madrid",
        "website": "https://www.duransubastas.com", 
        "description": "Casa de subastas española fundada en 1969, especializada en arte español y europeo.",
        "specialties": ["Arte Español", "Pintura Europea", "Antigüedades", "Joyería"],
        "established_year": 1969,
        "logo_url": "https://www.duransubastas.com/images/logo.png",
        "verified": True,
        "active": True
    },
    {
        "name": "Morton Subastas",
        "country": "México", 
        "city": "Ciudad de México",
        "website": "https://www.mortonsubastas.com",
        "description": "Casa de subastas mexicana especializada en arte mexicano y latinoamericano.",
        "specialties": ["Arte Mexicano", "Arte Latinoamericano", "Antigüedades"],
        "established_year": 1988,
        "logo_url": "https://www.mortonsubastas.com/images/logo.png",
        "verified": True,
        "active": True
    },
    {
        "name": "Setdart",
        "country": "España",
        "city": "Valencia", 
        "website": "https://www.setdart.com",
        "description": "Casa de subastas online española especializada en arte y antigüedades.",
        "specialties": ["Arte Contemporáneo", "Pintura", "Escultura", "Fotografía"],
        "established_year": 2010,
        "logo_url": "https://www.setdart.com/images/logo.png",
        "verified": True,
        "active": True
    },
    {
        "name": "Bonhams",
        "country": "United Kingdom",
        "city": "London",
        "website": "https://www.bonhams.com",
        "description": "Founded in 1793, Bonhams is one of the world's oldest and largest auctioneers.",
        "specialties": ["Fine Art", "Motor Cars", "Jewelry", "Asian Art"],
        "established_year": 1793, 
        "logo_url": "https://www.bonhams.com/images/logo.png",
        "verified": True,
        "active": True
    }
]

# Test data for artists
ARTISTS = [
    {
        "name": "Pablo Picasso",
        "birth_year": 1881,
        "death_year": 1973,
        "nationality": "Spanish",
        "biography": "Pablo Ruiz Picasso was a Spanish painter, sculptor, printmaker, ceramicist and theatre designer who spent most of his adult life in France.",
        "art_movement": "Cubism",
        "verified": True,
        "wikidata_id": "Q5593"
    },
    {
        "name": "Vincent van Gogh", 
        "birth_year": 1853,
        "death_year": 1890,
        "nationality": "Dutch",
        "biography": "Vincent Willem van Gogh was a Dutch post-impressionist painter who posthumously became one of the most famous and influential figures in the history of Western art.",
        "art_movement": "Post-Impressionism",
        "verified": True,
        "wikidata_id": "Q5582"
    },
    {
        "name": "Frida Kahlo",
        "birth_year": 1907,
        "death_year": 1954, 
        "nationality": "Mexican",
        "biography": "Frida Kahlo de Rivera was a Mexican painter known for her many portraits, self-portraits, and works inspired by the nature and artifacts of Mexico.",
        "art_movement": "Surrealism",
        "verified": True,
        "wikidata_id": "Q5588"
    },
    {
        "name": "Diego Velázquez",
        "birth_year": 1599,
        "death_year": 1660,
        "nationality": "Spanish", 
        "biography": "Diego Rodríguez de Silva y Velázquez was a Spanish painter, the leading artist in the court of King Philip IV and of the Spanish Golden Age.",
        "art_movement": "Baroque",
        "verified": True,
        "wikidata_id": "Q5593"
    },
    {
        "name": "Joan Miró",
        "birth_year": 1893,
        "death_year": 1983,
        "nationality": "Spanish",
        "biography": "Joan Miró i Ferrà was a Spanish painter, sculptor, and ceramicist born in Barcelona.",
        "art_movement": "Surrealism", 
        "verified": True,
        "wikidata_id": "Q5542"
    },
    {
        "name": "Francisco Goya",
        "birth_year": 1746,
        "death_year": 1828,
        "nationality": "Spanish",
        "biography": "Francisco José de Goya y Lucientes was a Spanish romantic painter and printmaker.",
        "art_movement": "Romanticism",
        "verified": True,
        "wikidata_id": "Q5432"
    },
    {
        "name": "Claude Monet",
        "birth_year": 1840,
        "death_year": 1926,
        "nationality": "French",
        "biography": "Oscar-Claude Monet was a French painter and founder of French Impressionist painting.",
        "art_movement": "Impressionism",
        "verified": True,
        "wikidata_id": "Q5594"
    },
    {
        "name": "Salvador Dalí",
        "birth_year": 1904,
        "death_year": 1989,
        "nationality": "Spanish", 
        "biography": "Salvador Domingo Felipe Jacinto Dalí i Domènech was a Spanish surrealist artist renowned for his technical skill.",
        "art_movement": "Surrealism",
        "verified": True,
        "wikidata_id": "Q5537"
    }
]

# Categories for artworks
CATEGORIES = [
    {"name": "Paintings", "description": "Oil paintings, watercolors, acrylics, and other painted works", "parent_id": None},
    {"name": "Sculptures", "description": "Three-dimensional artworks in various materials", "parent_id": None},
    {"name": "Prints", "description": "Lithographs, etchings, engravings, and other print media", "parent_id": None},
    {"name": "Photography", "description": "Photographic works and digital art", "parent_id": None},
    {"name": "Drawings", "description": "Sketches, studies, and finished drawings", "parent_id": None},
    {"name": "Oil Painting", "description": "Paintings created with oil-based paints", "parent_id": 1},
    {"name": "Watercolor", "description": "Paintings created with water-based paints", "parent_id": 1},
    {"name": "Bronze Sculpture", "description": "Sculptures cast in bronze", "parent_id": 2},
    {"name": "Marble Sculpture", "description": "Sculptures carved from marble", "parent_id": 2},
    {"name": "Lithograph", "description": "Prints made using lithographic process", "parent_id": 3}
]

async def create_connection():
    """Create database connection"""
    return await asyncpg.connect(DATABASE_URL)

async def populate_auction_houses(conn):
    """Insert test auction houses"""
    print("🏛️  Populating auction houses...")
    
    for house in AUCTION_HOUSES:
        await conn.execute("""
            INSERT INTO auction_houses (
                name, country, city, website, description, specialties,
                established_year, logo_url, verified, active, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
            ON CONFLICT (name) DO UPDATE SET
                country = EXCLUDED.country,
                city = EXCLUDED.city,
                website = EXCLUDED.website,
                description = EXCLUDED.description,
                updated_at = NOW()
        """, 
        house["name"], house["country"], house["city"], house["website"],
        house["description"], house["specialties"], house["established_year"],
        house["logo_url"], house["verified"], house["active"])
    
    print(f"✅ Inserted {len(AUCTION_HOUSES)} auction houses")

async def populate_artists(conn):
    """Insert test artists"""
    print("🎨 Populating artists...")
    
    for artist in ARTISTS:
        await conn.execute("""
            INSERT INTO artists (
                name, birth_year, death_year, nationality, biography,
                art_movement, verified, wikidata_id, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
            ON CONFLICT (name, birth_year) DO UPDATE SET
                biography = EXCLUDED.biography,
                art_movement = EXCLUDED.art_movement,
                updated_at = NOW()
        """,
        artist["name"], artist["birth_year"], artist["death_year"],
        artist["nationality"], artist["biography"], artist["art_movement"],
        artist["verified"], artist["wikidata_id"])
    
    print(f"✅ Inserted {len(ARTISTS)} artists")

async def populate_categories(conn):
    """Insert test categories"""
    print("📁 Populating categories...")
    
    for category in CATEGORIES:
        await conn.execute("""
            INSERT INTO categories (name, description, parent_id, created_at, updated_at)
            VALUES ($1, $2, $3, NOW(), NOW())
            ON CONFLICT (name) DO UPDATE SET
                description = EXCLUDED.description,
                updated_at = NOW()
        """, category["name"], category["description"], category["parent_id"])
    
    print(f"✅ Inserted {len(CATEGORIES)} categories")

async def populate_auctions(conn):
    """Create sample auctions"""
    print("🔨 Populating auctions...")
    
    # Get house IDs
    houses = await conn.fetch("SELECT id, name FROM auction_houses ORDER BY id")
    
    auction_templates = [
        {
            "title": "Important Modern & Contemporary Art",
            "description": "An exceptional selection of modern and contemporary masterpieces featuring works by leading international artists.",
            "auction_type": "live",
            "location": "New York",
            "currency": "USD"
        },
        {
            "title": "Impressionist & Modern Art Evening Sale", 
            "description": "Featuring exceptional works from the Impressionist and Modern periods, including masterpieces by Monet, Renoir, and Picasso.",
            "auction_type": "live",
            "location": "London", 
            "currency": "GBP"
        },
        {
            "title": "Arte Español y Europeo",
            "description": "Subasta especializada en pintura española de los siglos XIX y XX, incluyendo obras de grandes maestros.",
            "auction_type": "live",
            "location": "Madrid",
            "currency": "EUR"
        },
        {
            "title": "Arte Mexicano y Latinoamericano",
            "description": "Colección excepcional de arte mexicano featuring obras de Frida Kahlo, Diego Rivera y otros maestros.",
            "auction_type": "live", 
            "location": "Ciudad de México",
            "currency": "MXN"
        },
        {
            "title": "Contemporary Art Online",
            "description": "Online-only sale featuring emerging and established contemporary artists from around the world.",
            "auction_type": "online",
            "location": "Online",
            "currency": "EUR"
        }
    ]
    
    auction_count = 0
    for i, house in enumerate(houses):
        # Create 2-3 auctions per house
        num_auctions = random.randint(2, 3)
        
        for j in range(num_auctions):
            template = auction_templates[j % len(auction_templates)]
            
            # Generate dates
            days_ago = random.randint(-30, 90)  # Past 30 days to future 90 days
            start_date = datetime.now() + timedelta(days=days_ago)
            end_date = start_date + timedelta(hours=random.randint(2, 8))
            
            # Exhibition dates (usually before auction)
            exhibition_start = start_date - timedelta(days=random.randint(3, 14))
            exhibition_end = start_date - timedelta(days=1)
            
            # Status based on date
            if days_ago < -1:
                status = "completed"
            elif days_ago <= 7:
                status = "upcoming" 
            else:
                status = "preview"
            
            title = f"{house['name']} - {template['title']}"
            if j > 0:
                title += f" ({j + 1})"
            
            slug = title.lower().replace(" ", "-").replace("&", "and")[:100]
            
            await conn.execute("""
                INSERT INTO auctions (
                    house_id, title, description, start_date, end_date,
                    exhibition_start, exhibition_end, status, location,
                    auction_type, slug, external_id, currency,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW(), NOW())
            """,
            house["id"], title, template["description"], start_date, end_date,
            exhibition_start, exhibition_end, status, template["location"], 
            template["auction_type"], slug, f"ext_{house['id']}_{j+1}",
            template["currency"])
            
            auction_count += 1
    
    print(f"✅ Inserted {auction_count} auctions")

async def populate_lots(conn):
    """Create sample lots/artworks"""
    print("🖼️  Populating lots...")
    
    # Get reference data
    auctions = await conn.fetch("SELECT id, house_id, currency, status FROM auctions ORDER BY id")
    artists = await conn.fetch("SELECT id, name FROM artists ORDER BY id") 
    categories = await conn.fetch("SELECT id, name FROM categories WHERE parent_id IS NOT NULL ORDER BY id")
    
    lot_templates = [
        {
            "title": "Untitled (Blue Period)",
            "medium": "Oil on canvas",
            "dimensions": "73 x 60 cm",
            "description": "A rare work from the artist's most celebrated period, showcasing exceptional technique and emotional depth."
        },
        {
            "title": "Still Life with Flowers",
            "medium": "Oil on canvas", 
            "dimensions": "65 x 50 cm",
            "description": "Vibrant still life composition demonstrating the artist's mastery of color and light."
        },
        {
            "title": "Portrait of a Lady",
            "medium": "Oil on canvas",
            "dimensions": "81 x 65 cm", 
            "description": "Elegant portrait showcasing the refinement and technical skill characteristic of the period."
        },
        {
            "title": "Landscape with Trees",
            "medium": "Oil on canvas",
            "dimensions": "92 x 73 cm",
            "description": "Atmospheric landscape capturing the changing light and natural beauty of the countryside."
        },
        {
            "title": "Abstract Composition",
            "medium": "Mixed media on canvas",
            "dimensions": "120 x 100 cm",
            "description": "Bold abstract work exploring color, form, and artistic expression."
        }
    ]
    
    lot_count = 0
    for auction in auctions:
        # Create 8-25 lots per auction
        num_lots = random.randint(8, 25)
        
        for lot_num in range(1, num_lots + 1):
            template = lot_templates[lot_num % len(lot_templates)]
            artist = random.choice(artists)
            category = random.choice(categories)
            
            # Generate pricing based on currency
            currency_multipliers = {"USD": 1, "EUR": 0.85, "GBP": 0.75, "MXN": 20}
            multiplier = currency_multipliers.get(auction["currency"], 1)
            
            base_min = random.randint(1000, 50000)
            estimate_min = int(base_min * multiplier)
            estimate_max = int(estimate_min * random.uniform(1.5, 3.0))
            
            # Final price and sold status based on auction status
            sold = False
            final_price = None
            
            if auction["status"] == "completed":
                sold = random.choice([True, True, True, False])  # 75% sold rate
                if sold:
                    # Final price usually within or above estimate range
                    price_factor = random.uniform(0.8, 2.5)
                    final_price = int(estimate_min * price_factor)
            
            title = f"{template['title']} #{lot_num}"
            if artist["name"] in ["Pablo Picasso", "Vincent van Gogh"]:
                title = f"{template['title']}"  # Remove number for famous artists
            
            # Some lots get images
            images = None
            if random.random() < 0.3:  # 30% chance of having image
                images = [f"https://example.com/images/lot_{auction['id']}_{lot_num}.jpg"]
            
            external_url = f"https://example.com/lots/{auction['id']}/{lot_num}"
            
            await conn.execute("""
                INSERT INTO lots (
                    auction_id, artist_id, category_id, lot_number, title,
                    description, medium, dimensions, estimated_price_min,
                    estimated_price_max, final_price, sold, currency,
                    images, external_url, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, NOW(), NOW())
            """,
            auction["id"], artist["id"], category["id"], str(lot_num), 
            title, template["description"], template["medium"], 
            template["dimensions"], Decimal(str(estimate_min)), 
            Decimal(str(estimate_max)), 
            Decimal(str(final_price)) if final_price else None,
            sold, auction["currency"], images, external_url)
            
            lot_count += 1
    
    print(f"✅ Inserted {lot_count} lots")

async def update_auction_statistics(conn):
    """Update auction statistics based on lots"""
    print("📊 Updating auction statistics...")
    
    await conn.execute("""
        UPDATE auctions SET
            total_lots = (SELECT COUNT(*) FROM lots WHERE lots.auction_id = auctions.id),
            total_estimate_min = (SELECT SUM(estimated_price_min) FROM lots WHERE lots.auction_id = auctions.id),
            total_estimate_max = (SELECT SUM(estimated_price_max) FROM lots WHERE lots.auction_id = auctions.id),
            total_realized = (SELECT SUM(final_price) FROM lots WHERE lots.auction_id = auctions.id AND sold = true),
            sale_rate = (
                SELECT CASE 
                    WHEN COUNT(*) > 0 THEN ROUND((COUNT(*) FILTER (WHERE sold = true) * 100.0 / COUNT(*)), 2)
                    ELSE 0
                END
                FROM lots WHERE lots.auction_id = auctions.id
            ),
            updated_at = NOW()
    """)
    
    print("✅ Updated auction statistics")

async def main():
    """Main function to populate all test data"""
    print("🚀 Starting database population with test data...\n")
    
    try:
        conn = await create_connection()
        print("✅ Connected to database\n")
        
        # Populate in order (respecting foreign key constraints)
        await populate_auction_houses(conn)
        await populate_artists(conn) 
        await populate_categories(conn)
        await populate_auctions(conn)
        await populate_lots(conn)
        await update_auction_statistics(conn)
        
        # Summary statistics
        houses_count = await conn.fetchval("SELECT COUNT(*) FROM auction_houses")
        auctions_count = await conn.fetchval("SELECT COUNT(*) FROM auctions")  
        artists_count = await conn.fetchval("SELECT COUNT(*) FROM artists")
        lots_count = await conn.fetchval("SELECT COUNT(*) FROM lots")
        categories_count = await conn.fetchval("SELECT COUNT(*) FROM categories")
        
        print(f"\n🎉 Database population completed successfully!")
        print(f"📈 Summary:")
        print(f"   • {houses_count} auction houses")
        print(f"   • {auctions_count} auctions") 
        print(f"   • {artists_count} artists")
        print(f"   • {lots_count} lots/artworks")
        print(f"   • {categories_count} categories")
        print(f"\n🌐 You can now test the API endpoints:")
        print(f"   • GET /api/v1/houses/ - List all auction houses")
        print(f"   • GET /api/v1/auctions/ - List all auctions")
        print(f"   • GET /api/v1/lots/ - List all art lots") 
        print(f"   • GET /api/v1/artists/ - List all artists")
        print(f"   • GET /docs - Interactive API documentation")
        
    except Exception as e:
        print(f"❌ Error populating database: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())