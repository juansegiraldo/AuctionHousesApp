-- Auction Houses Database Schema
-- Initial migration script

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Auction Houses table
CREATE TABLE auction_houses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(100) NOT NULL,
    website VARCHAR(500) NOT NULL,
    description TEXT,
    scraping_config JSONB DEFAULT '{}',
    last_scrape TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'maintenance')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(name, country)
);

-- Categories table (hierarchical)
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    parent_category_id INTEGER REFERENCES categories(id),
    level INTEGER DEFAULT 0,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(name, parent_category_id)
);

-- Artists table
CREATE TABLE artists (
    id SERIAL PRIMARY KEY,
    name VARCHAR(300) NOT NULL,
    birth_year INTEGER,
    death_year INTEGER,
    nationality VARCHAR(100),
    movement VARCHAR(100),
    biography TEXT,
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Auctions table
CREATE TABLE auctions (
    id SERIAL PRIMARY KEY,
    house_id INTEGER NOT NULL REFERENCES auction_houses(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    exhibition_start TIMESTAMP,
    exhibition_end TIMESTAMP,
    status VARCHAR(20) DEFAULT 'upcoming' CHECK (status IN ('upcoming', 'active', 'completed', 'cancelled')),
    location VARCHAR(200),
    auction_type VARCHAR(50) DEFAULT 'live' CHECK (auction_type IN ('live', 'online', 'hybrid')),
    slug VARCHAR(300),
    external_id VARCHAR(100),
    total_lots INTEGER DEFAULT 0,
    total_estimate_min DECIMAL(15,2),
    total_estimate_max DECIMAL(15,2),
    total_realized DECIMAL(15,2),
    currency VARCHAR(3) DEFAULT 'USD',
    sale_rate DECIMAL(5,2), -- percentage of lots sold
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(house_id, external_id)
);

-- Lots table
CREATE TABLE lots (
    id SERIAL PRIMARY KEY,
    auction_id INTEGER NOT NULL REFERENCES auctions(id) ON DELETE CASCADE,
    lot_number VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    artist_id INTEGER REFERENCES artists(id),
    category_id INTEGER REFERENCES categories(id),
    estimated_price_min DECIMAL(12,2),
    estimated_price_max DECIMAL(12,2),
    final_price DECIMAL(12,2),
    hammer_price DECIMAL(12,2),
    buyers_premium DECIMAL(12,2),
    currency VARCHAR(3) DEFAULT 'USD',
    sold BOOLEAN DEFAULT FALSE,
    images JSONB DEFAULT '[]',
    dimensions VARCHAR(200),
    medium VARCHAR(200),
    provenance TEXT,
    exhibition_history TEXT,
    literature TEXT,
    condition_report TEXT,
    signature TEXT,
    external_id VARCHAR(100),
    external_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(auction_id, lot_number)
);

-- Scraping logs table
CREATE TABLE scraping_logs (
    id SERIAL PRIMARY KEY,
    house_id INTEGER REFERENCES auction_houses(id),
    task_type VARCHAR(50) NOT NULL, -- 'auctions', 'lots', 'full'
    status VARCHAR(20) NOT NULL CHECK (status IN ('started', 'completed', 'failed', 'cancelled')),
    start_time TIMESTAMP DEFAULT NOW(),
    end_time TIMESTAMP,
    items_processed INTEGER DEFAULT 0,
    items_created INTEGER DEFAULT 0,
    items_updated INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);

-- Performance indexes
CREATE INDEX idx_auction_houses_country ON auction_houses(country);
CREATE INDEX idx_auction_houses_status ON auction_houses(status);
CREATE INDEX idx_auction_houses_last_scrape ON auction_houses(last_scrape);

CREATE INDEX idx_auctions_house_id ON auctions(house_id);
CREATE INDEX idx_auctions_status ON auctions(status);
CREATE INDEX idx_auctions_start_date ON auctions(start_date DESC);
CREATE INDEX idx_auctions_house_date ON auctions(house_id, start_date DESC);

CREATE INDEX idx_lots_auction_id ON lots(auction_id);
CREATE INDEX idx_lots_artist_id ON lots(artist_id);
CREATE INDEX idx_lots_category_id ON lots(category_id);
CREATE INDEX idx_lots_final_price ON lots(final_price DESC) WHERE final_price IS NOT NULL;
CREATE INDEX idx_lots_sold ON lots(sold);
CREATE INDEX idx_lots_title_gin ON lots USING gin(to_tsvector('english', title));
CREATE INDEX idx_lots_description_gin ON lots USING gin(to_tsvector('english', description));

CREATE INDEX idx_artists_name ON artists(name);
CREATE INDEX idx_artists_nationality ON artists(nationality);

CREATE INDEX idx_categories_parent ON categories(parent_category_id);

CREATE INDEX idx_scraping_logs_house_time ON scraping_logs(house_id, start_time DESC);

-- Full-text search indexes
CREATE INDEX idx_artists_search ON artists USING gin(to_tsvector('english', name || ' ' || COALESCE(nationality, '')));

-- Update triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_auction_houses_updated_at BEFORE UPDATE ON auction_houses FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_auctions_updated_at BEFORE UPDATE ON auctions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_lots_updated_at BEFORE UPDATE ON lots FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_artists_updated_at BEFORE UPDATE ON artists FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();