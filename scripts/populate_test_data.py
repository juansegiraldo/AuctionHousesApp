#!/usr/bin/env python3
"""
Script to populate the database with test data
This will create sample auctions and lots for testing purposes
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

# Add the backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.core.database import database
from app.services.houses import HouseService
from app.services.auctions import AuctionService
from app.services.lots import LotService
from app.services.artists import ArtistService
from app.models.schemas import AuctionCreate, LotCreate, ArtistCreate

async def create_test_data():
    """Create test auctions and lots"""
    
    try:
        await database.connect()
        print("🔗 Connected to database")
        
        # Check if we have auction houses
        houses = await HouseService.get_houses(database, limit=5)
        if not houses:
            print("❌ No auction houses found. Please run database migrations first.")
            return
        
        print(f"✅ Found {len(houses)} auction houses")
        
        # Create test auctions for the first few houses
        auctions_created = 0
        lots_created = 0
        
        for house in houses[:3]:  # First 3 houses
            print(f"\n📦 Creating test data for {house.name}")
            
            # Create 2-3 test auctions per house
            for i in range(2):
                start_date = datetime.utcnow() + timedelta(days=i*30)
                end_date = start_date + timedelta(days=3)
                
                auction_data = AuctionCreate(
                    house_id=house.id,
                    title=f"Test Auction {i+1} - {house.name}",
                    description=f"Sample auction for testing purposes. Featuring contemporary art and collectibles.",
                    start_date=start_date,
                    end_date=end_date,
                    location=f"{house.country}",
                    auction_type="hybrid",
                    slug=f"test-auction-{house.id}-{i+1}",
                    external_id=f"TEST_{house.id}_{i+1}"
                )
                
                try:
                    auction = await AuctionService.create_auction(database, auction_data)
                    auctions_created += 1
                    print(f"  ✅ Created auction: {auction.title}")
                    
                    # Create 10-15 test lots per auction
                    for j in range(10):
                        # Create or get artist
                        artist_names = [
                            "Pablo Picasso", "Diego Rivera", "Frida Kahlo", "Fernando Botero",
                            "Salvador Dalí", "Andy Warhol", "Jean-Michel Basquiat", "David Hockney",
                            "Yves Klein", "Jackson Pollock"
                        ]
                        
                        artist_name = artist_names[j % len(artist_names)]
                        artist = await ArtistService.find_or_create_artist(database, artist_name)
                        
                        # Generate lot data
                        min_price = 1000 + (j * 500)
                        max_price = min_price + 2000
                        
                        lot_data = LotCreate(
                            auction_id=auction.id,
                            lot_number=f"{j+1:03d}",
                            title=f"Artwork by {artist_name} #{j+1}",
                            description=f"Beautiful piece by renowned artist {artist_name}. Mixed media on canvas.",
                            artist_id=artist.id,
                            estimated_price_min=Decimal(str(min_price)),
                            estimated_price_max=Decimal(str(max_price)),
                            dimensions="50 x 70 cm",
                            medium="Mixed media",
                            external_id=f"LOT_{auction.id}_{j+1:03d}",
                            currency="USD" if house.country == "Estados Unidos" else "COP"
                        )
                        
                        try:
                            lot = await LotService.create_lot(database, lot_data)
                            lots_created += 1
                        except Exception as e:
                            print(f"    ⚠️ Error creating lot {j+1}: {e}")
                    
                    print(f"  ✅ Created {10} lots for auction")
                    
                except Exception as e:
                    print(f"  ❌ Error creating auction: {e}")
        
        print(f"\n🎉 Test data creation completed!")
        print(f"   📊 Created {auctions_created} auctions")
        print(f"   🎨 Created {lots_created} lots")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await database.disconnect()

async def create_sample_sold_lots():
    """Mark some lots as sold with final prices"""
    try:
        await database.connect()
        
        # Get some lots to mark as sold
        lots = await LotService.get_lots(database, filters={}, limit=20)
        
        sold_count = 0
        for i, lot in enumerate(lots):
            if i % 3 == 0:  # Mark every 3rd lot as sold
                # Calculate a final price within the estimate range
                if lot.estimated_price_min and lot.estimated_price_max:
                    final_price = (lot.estimated_price_min + lot.estimated_price_max) / 2
                    final_price = final_price * Decimal(str(1.1))  # 10% above mid-estimate
                    
                    update_data = {
                        "final_price": final_price,
                        "sold": True
                    }
                    
                    try:
                        await LotService.update_lot(database, lot.id, update_data)
                        sold_count += 1
                    except Exception as e:
                        print(f"Error updating lot {lot.id}: {e}")
        
        print(f"✅ Marked {sold_count} lots as sold")
        
    except Exception as e:
        print(f"❌ Error updating sold lots: {e}")
    finally:
        await database.disconnect()

def main():
    """Main function"""
    print("🧪 Creating test data for Auction Houses API")
    print("=" * 50)
    
    # Create test data
    asyncio.run(create_test_data())
    
    # Mark some lots as sold
    print("\n📈 Creating sales data...")
    asyncio.run(create_sample_sold_lots())
    
    print("\n" + "=" * 50)
    print("✅ Test data creation complete!")
    print("You can now test the API endpoints with realistic data.")

if __name__ == "__main__":
    main()