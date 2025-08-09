#!/usr/bin/env python3
"""
Railway database initialization script
This script will initialize the PostgreSQL database on Railway
"""

import asyncio
import os
import sys
import logging

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_railway_db():
    """Initialize Railway database with schema and seed data"""
    try:
        # Import after adding to path
        from app.core.database import database
        from sqlalchemy import text
        
        logger.info("🔄 Connecting to Railway database...")
        await database.connect()
        logger.info("✅ Connected to database")
        
        # Check if tables already exist
        check_query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'auction_houses'
        );
        """
        
        exists = await database.fetch_val(check_query)
        if exists:
            logger.info("✅ Database already initialized")
            return
        
        logger.info("🔄 Creating database schema...")
        
        # Read and execute schema file
        migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'database', 'migrations')
        schema_file = os.path.join(migrations_dir, '001_initial_schema.sql')
        
        if os.path.exists(schema_file):
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            # Execute schema (split by statements ending with ;)
            statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
            
            for i, statement in enumerate(statements):
                try:
                    await database.execute(text(statement))
                    logger.info(f"✅ Executed statement {i+1}/{len(statements)}")
                except Exception as e:
                    logger.warning(f"⚠️ Statement {i+1} failed: {e}")
            
            logger.info("✅ Schema created successfully")
        else:
            logger.error(f"❌ Schema file not found: {schema_file}")
            return
        
        # Read and execute seed data
        logger.info("🔄 Inserting seed data...")
        seeds_dir = os.path.join(os.path.dirname(__file__), '..', 'database', 'seeds')
        seed_file = os.path.join(seeds_dir, '002_auction_houses_data.sql')
        
        if os.path.exists(seed_file):
            with open(seed_file, 'r', encoding='utf-8') as f:
                seed_sql = f.read()
            
            # Execute seed data
            statements = [stmt.strip() for stmt in seed_sql.split(';') if stmt.strip()]
            
            for i, statement in enumerate(statements):
                try:
                    await database.execute(text(statement))
                    logger.info(f"✅ Executed seed statement {i+1}/{len(statements)}")
                except Exception as e:
                    logger.warning(f"⚠️ Seed statement {i+1} failed: {e}")
            
            logger.info("✅ Seed data inserted successfully")
        else:
            logger.warning(f"⚠️ Seed file not found: {seed_file}")
        
        # Verify data
        verify_query = "SELECT COUNT(*) FROM auction_houses"
        count = await database.fetch_val(verify_query)
        logger.info(f"✅ Verification: {count} auction houses in database")
        
        logger.info("🎉 Railway database initialization complete!")
        
    except Exception as e:
        logger.error(f"❌ Error initializing Railway database: {e}")
        raise
    finally:
        try:
            await database.disconnect()
            logger.info("🔌 Disconnected from database")
        except:
            pass

def main():
    """Main function for Railway database initialization"""
    logger.info("🚂 Railway Database Initialization")
    logger.info("=" * 50)
    
    # Check if we're on Railway
    if not os.getenv("RAILWAY_ENVIRONMENT"):
        logger.warning("⚠️ Not running on Railway, but proceeding...")
    
    # Check for DATABASE_URL
    if not os.getenv("DATABASE_URL"):
        logger.error("❌ DATABASE_URL not found. Make sure PostgreSQL is connected in Railway.")
        sys.exit(1)
    
    try:
        asyncio.run(init_railway_db())
        logger.info("✅ Database initialization successful!")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()