#!/usr/bin/env python3
"""
Simplified version using SQLite and in-memory data
Perfect for testing without external dependencies
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import uvicorn

# Simple data models
class AuctionHouse(BaseModel):
    id: int
    name: str
    country: str
    website: str
    description: str = ""

class Auction(BaseModel):
    id: int
    house_id: int
    house_name: str
    title: str
    start_date: Optional[str] = None
    status: str = "upcoming"

class Lot(BaseModel):
    id: int
    auction_id: int
    lot_number: str
    title: str
    artist_name: Optional[str] = None
    estimated_price: Optional[float] = None

# Create FastAPI app
app = FastAPI(
    title="Auction Houses API - Simplified",
    description="Simplified version for testing without Docker",
    version="1.0.0-simple"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQLite database setup
DB_FILE = "auction_houses_simple.db"

def init_database():
    """Initialize SQLite database with sample data"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auction_houses (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            website TEXT NOT NULL,
            description TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auctions (
            id INTEGER PRIMARY KEY,
            house_id INTEGER,
            title TEXT NOT NULL,
            start_date TEXT,
            status TEXT DEFAULT 'upcoming',
            FOREIGN KEY (house_id) REFERENCES auction_houses (id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lots (
            id INTEGER PRIMARY KEY,
            auction_id INTEGER,
            lot_number TEXT NOT NULL,
            title TEXT NOT NULL,
            artist_name TEXT,
            estimated_price REAL,
            FOREIGN KEY (auction_id) REFERENCES auctions (id)
        )
    """)
    
    # Insert sample data if empty
    cursor.execute("SELECT COUNT(*) FROM auction_houses")
    if cursor.fetchone()[0] == 0:
        # Sample auction houses
        houses = [
            (1, "Bogotá Auctions", "Colombia", "https://www.bogotaauctions.com", "Colombian auction house"),
            (2, "Durán Subastas", "España", "https://www.duran-subastas.com", "Spain's oldest auction house"),
            (3, "Morton Subastas", "México", "https://www.mortonsubastas.com", "Mexican auction house"),
            (4, "Christie's", "Estados Unidos", "https://www.christies.com", "International auction house")
        ]
        cursor.executemany("INSERT INTO auction_houses VALUES (?, ?, ?, ?, ?)", houses)
        
        # Sample auctions
        auctions = [
            (1, 1, "Arte Latinoamericano", "2025-09-15", "upcoming"),
            (2, 1, "Libros y Grabados", "2025-08-20", "active"),
            (3, 2, "Arte Contemporáneo", "2025-09-01", "upcoming"),
            (4, 3, "Colección Especial", "2025-08-25", "upcoming")
        ]
        cursor.executemany("INSERT INTO auctions VALUES (?, ?, ?, ?, ?)", auctions)
        
        # Sample lots
        lots = [
            (1, 1, "001", "Paisaje Colombiano", "Fernando Botero", 15000),
            (2, 1, "002", "Naturaleza Muerta", "Alejandro Obregón", 8000),
            (3, 2, "003", "Grabado Histórico", "Autor Desconocido", 2000),
            (4, 3, "004", "Obra Abstracta", "Eduardo Chillida", 25000),
            (5, 4, "005", "Retrato", "Diego Rivera", 50000)
        ]
        cursor.executemany("INSERT INTO lots VALUES (?, ?, ?, ?, ?, ?)", lots)
    
    conn.commit()
    conn.close()

# API Endpoints
@app.on_event("startup")
async def startup():
    init_database()

@app.get("/")
async def root():
    return {
        "message": "Auction Houses API - Simplified Version",
        "version": "1.0.0-simple",
        "docs": "/docs",
        "status": "running"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "database": "sqlite",
        "version": "1.0.0-simple"
    }

@app.get("/api/v1/houses/", response_model=List[AuctionHouse])
async def get_houses():
    """Get all auction houses"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM auction_houses")
    rows = cursor.fetchall()
    conn.close()
    
    return [
        AuctionHouse(
            id=row[0], name=row[1], country=row[2], 
            website=row[3], description=row[4] or ""
        )
        for row in rows
    ]

@app.get("/api/v1/houses/{house_id}", response_model=AuctionHouse)
async def get_house(house_id: int):
    """Get specific auction house"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM auction_houses WHERE id = ?", (house_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="House not found")
    
    return AuctionHouse(
        id=row[0], name=row[1], country=row[2],
        website=row[3], description=row[4] or ""
    )

@app.get("/api/v1/auctions/", response_model=List[Auction])
async def get_auctions():
    """Get all auctions"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.house_id, a.title, a.start_date, a.status, h.name
        FROM auctions a
        JOIN auction_houses h ON a.house_id = h.id
    """)
    rows = cursor.fetchall()
    conn.close()
    
    return [
        Auction(
            id=row[0], house_id=row[1], title=row[2],
            start_date=row[3], status=row[4], house_name=row[5]
        )
        for row in rows
    ]

@app.get("/api/v1/auctions/{auction_id}", response_model=Auction)
async def get_auction(auction_id: int):
    """Get specific auction"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.house_id, a.title, a.start_date, a.status, h.name
        FROM auctions a
        JOIN auction_houses h ON a.house_id = h.id
        WHERE a.id = ?
    """, (auction_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Auction not found")
    
    return Auction(
        id=row[0], house_id=row[1], title=row[2],
        start_date=row[3], status=row[4], house_name=row[5]
    )

@app.get("/api/v1/lots/", response_model=List[Lot])
async def get_lots():
    """Get all lots"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lots")
    rows = cursor.fetchall()
    conn.close()
    
    return [
        Lot(
            id=row[0], auction_id=row[1], lot_number=row[2],
            title=row[3], artist_name=row[4], estimated_price=row[5]
        )
        for row in rows
    ]

@app.get("/api/v1/lots/search/")
async def search_lots(q: str):
    """Search lots by title or artist"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM lots 
        WHERE title LIKE ? OR artist_name LIKE ?
    """, (f"%{q}%", f"%{q}%"))
    rows = cursor.fetchall()
    conn.close()
    
    return [
        Lot(
            id=row[0], auction_id=row[1], lot_number=row[2],
            title=row[3], artist_name=row[4], estimated_price=row[5]
        )
        for row in rows
    ]

@app.get("/api/v1/analytics/summary/")
async def get_summary():
    """Get summary statistics"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM auction_houses")
    houses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM auctions")
    auctions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM lots")
    lots = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(estimated_price) FROM lots WHERE estimated_price IS NOT NULL")
    total_value = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_houses": houses,
        "total_auctions": auctions,
        "total_lots": lots,
        "total_estimated_value": total_value or 0,
        "version": "simplified"
    }

def main():
    """Run the simplified app"""
    print("🚀 Starting Auction Houses API - Simplified Version")
    print("=" * 50)
    print("📍 API will be available at:")
    print("   • Documentation: http://localhost:8000/docs")
    print("   • API Base: http://localhost:8000/api/v1")
    print("   • Health: http://localhost:8000/health")
    print("\n🎯 This version uses SQLite and requires no external services!")
    print("=" * 50)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True
    )

if __name__ == "__main__":
    main()