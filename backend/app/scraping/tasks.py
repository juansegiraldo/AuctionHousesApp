from celery import Task
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
from databases import Database

from app.core.celery_app import celery_app
from app.core.database import database
from app.services.houses import HouseService
from app.services.auctions import AuctionService
from app.services.lots import LotService
from app.services.artists import ArtistService
from app.scraping.adapters.bogota_auctions import BogotaAuctionsAdapter
from app.scraping.base_adapter import BaseScrapingAdapter, AuctionData, LotData
from app.models.schemas import AuctionCreate, LotCreate

logger = logging.getLogger(__name__)

class ScrapingTask(Task):
    """Base task class for scraping operations"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure"""
        logger.error(f"Scraping task {task_id} failed: {exc}")
        
    def on_success(self, retval, task_id, args, kwargs):
        """Log task success"""
        logger.info(f"Scraping task {task_id} completed successfully")

@celery_app.task(base=ScrapingTask, bind=True, max_retries=3)
def scrape_house_data(self, house_id: int) -> Dict[str, Any]:
    """
    Main task to scrape all data for a specific auction house
    """
    start_time = datetime.utcnow()
    result = {
        "house_id": house_id,
        "start_time": start_time.isoformat(),
        "status": "started",
        "auctions_scraped": 0,
        "lots_scraped": 0,
        "errors": []
    }
    
    try:
        # Connect to database
        await database.connect()
        
        # Get house configuration
        house = await HouseService.get_house_by_id(database, house_id)
        if not house:
            raise Exception(f"House with ID {house_id} not found")
        
        # Log scraping start
        await _log_scraping_start(database, house_id, "full")
        
        # Get appropriate adapter
        adapter = _get_adapter_for_house(house)
        if not adapter:
            raise Exception(f"No adapter available for house: {house.name}")
        
        logger.info(f"Starting scraping for {house.name} using {adapter.__class__.__name__}")
        
        # Scrape auctions
        auctions = await adapter.scrape_auctions()
        result["auctions_found"] = len(auctions)
        
        # Process each auction
        for auction_data in auctions:
            try:
                # Save auction to database
                auction = await _save_auction(database, house_id, auction_data)
                if auction:
                    result["auctions_scraped"] += 1
                    
                    # Scrape lots for this auction
                    lots = await adapter.scrape_lots(auction_data)
                    
                    # Process lots
                    for lot_data in lots:
                        try:
                            # Find or create artist if specified
                            artist_id = None
                            if lot_data.artist_name:
                                artist = await ArtistService.find_or_create_artist(
                                    database, lot_data.artist_name
                                )
                                artist_id = artist.id
                            
                            # Save lot
                            lot = await _save_lot(database, auction.id, lot_data, artist_id)
                            if lot:
                                result["lots_scraped"] += 1
                                
                        except Exception as e:
                            error_msg = f"Error processing lot {lot_data.lot_number}: {e}"
                            logger.error(error_msg)
                            result["errors"].append(error_msg)
                            
            except Exception as e:
                error_msg = f"Error processing auction {auction_data.title}: {e}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
        
        # Update house last_scrape timestamp
        await HouseService.update_last_scrape(database, house_id)
        
        # Log scraping completion
        await _log_scraping_completion(
            database, house_id, "full", "completed", 
            result["auctions_scraped"], result["lots_scraped"]
        )
        
        result["status"] = "completed"
        result["end_time"] = datetime.utcnow().isoformat()
        
        logger.info(f"Completed scraping for {house.name}: "
                   f"{result['auctions_scraped']} auctions, {result['lots_scraped']} lots")
        
    except Exception as e:
        error_msg = f"Fatal error in scraping task: {e}"
        logger.error(error_msg)
        result["status"] = "failed"
        result["error"] = error_msg
        result["errors"].append(error_msg)
        
        # Log scraping failure
        try:
            await _log_scraping_completion(
                database, house_id, "full", "failed", 
                result.get("auctions_scraped", 0), result.get("lots_scraped", 0),
                error_message=error_msg
            )
        except:
            pass  # Don't fail on logging failure
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying scraping task for house {house_id} "
                       f"(attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(countdown=60 * (self.request.retries + 1))
    
    finally:
        await database.disconnect()
    
    return result

@celery_app.task
def schedule_daily_scraping():
    """Schedule scraping tasks for all houses with daily frequency"""
    try:
        # Get houses that should be scraped daily
        daily_houses = [1, 3, 4]  # Bogotá Auctions, Setdart, Morton (based on config)
        
        for house_id in daily_houses:
            scrape_house_data.delay(house_id)
            
        logger.info(f"Scheduled daily scraping for {len(daily_houses)} houses")
        return {"scheduled_houses": len(daily_houses), "house_ids": daily_houses}
        
    except Exception as e:
        logger.error(f"Error scheduling daily scraping: {e}")
        return {"error": str(e)}

@celery_app.task  
def schedule_weekly_scraping():
    """Schedule scraping tasks for all houses with weekly frequency"""
    try:
        # Get houses that should be scraped weekly
        weekly_houses = [2, 5, 10]  # Lefebre, Ansorena, Casa Saráchaga
        
        for house_id in weekly_houses:
            scrape_house_data.delay(house_id)
            
        logger.info(f"Scheduled weekly scraping for {len(weekly_houses)} houses")
        return {"scheduled_houses": len(weekly_houses), "house_ids": weekly_houses}
        
    except Exception as e:
        logger.error(f"Error scheduling weekly scraping: {e}")
        return {"error": str(e)}

@celery_app.task
def scrape_single_auction(auction_url: str, house_id: int) -> Dict[str, Any]:
    """Scrape a single auction and its lots"""
    try:
        await database.connect()
        
        house = await HouseService.get_house_by_id(database, house_id)
        if not house:
            raise Exception(f"House with ID {house_id} not found")
        
        adapter = _get_adapter_for_house(house)
        if not adapter:
            raise Exception(f"No adapter available for house: {house.name}")
        
        # Create auction data from URL
        auction_data = AuctionData(
            external_url=auction_url,
            title="Single Auction Scrape",
            status="active"
        )
        
        # Scrape lots
        lots = await adapter.scrape_lots(auction_data)
        
        return {
            "auction_url": auction_url,
            "lots_found": len(lots),
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"Error scraping single auction {auction_url}: {e}")
        return {"error": str(e), "status": "failed"}
    finally:
        await database.disconnect()

def _get_adapter_for_house(house) -> Optional[BaseScrapingAdapter]:
    """Get the appropriate scraping adapter for a house"""
    
    strategy = house.scraping_config.get("strategy", "")
    
    if house.name == "Bogotá Auctions" or strategy == "html_static":
        return BogotaAuctionsAdapter(house.scraping_config)
    
    # Add more adapters as they are implemented
    # elif house.name == "Durán Arte y Subastas":
    #     return DuranSubastasAdapter(house.scraping_config)
    # elif house.name == "Setdart":
    #     return SetdartAdapter(house.scraping_config)
    
    logger.warning(f"No adapter available for house: {house.name}")
    return None

async def _save_auction(db: Database, house_id: int, auction_data: AuctionData) -> Optional[Any]:
    """Save auction data to database"""
    try:
        # Check if auction already exists
        existing_query = """
            SELECT id FROM auctions 
            WHERE house_id = :house_id AND external_id = :external_id
        """
        existing = await db.fetch_one(existing_query, {
            "house_id": house_id,
            "external_id": auction_data.external_id
        })
        
        if existing:
            logger.debug(f"Auction already exists: {auction_data.title}")
            return existing
        
        # Create new auction
        auction_create = AuctionCreate(
            house_id=house_id,
            title=auction_data.title,
            description=auction_data.description,
            start_date=auction_data.start_date,
            end_date=auction_data.end_date,
            location=auction_data.location,
            auction_type=auction_data.auction_type,
            slug=auction_data.slug,
            external_id=auction_data.external_id
        )
        
        return await AuctionService.create_auction(db, auction_create)
        
    except Exception as e:
        logger.error(f"Error saving auction {auction_data.title}: {e}")
        return None

async def _save_lot(db: Database, auction_id: int, lot_data: LotData, artist_id: Optional[int] = None) -> Optional[Any]:
    """Save lot data to database"""
    try:
        # Check if lot already exists
        existing_query = """
            SELECT id FROM lots 
            WHERE auction_id = :auction_id AND lot_number = :lot_number
        """
        existing = await db.fetch_one(existing_query, {
            "auction_id": auction_id,
            "lot_number": lot_data.lot_number
        })
        
        if existing:
            logger.debug(f"Lot already exists: {lot_data.lot_number}")
            return existing
        
        # Create new lot
        lot_create = LotCreate(
            auction_id=auction_id,
            lot_number=lot_data.lot_number,
            title=lot_data.title,
            description=lot_data.description,
            artist_id=artist_id,
            estimated_price_min=lot_data.estimated_price_min,
            estimated_price_max=lot_data.estimated_price_max,
            dimensions=lot_data.dimensions,
            medium=lot_data.medium,
            external_id=lot_data.external_id,
            external_url=lot_data.external_url,
            currency=lot_data.currency
        )
        
        return await LotService.create_lot(db, lot_create)
        
    except Exception as e:
        logger.error(f"Error saving lot {lot_data.lot_number}: {e}")
        return None

async def _log_scraping_start(db: Database, house_id: int, task_type: str):
    """Log the start of a scraping task"""
    query = """
        INSERT INTO scraping_logs (house_id, task_type, status, start_time)
        VALUES (:house_id, :task_type, 'started', NOW())
    """
    
    await db.execute(query, {
        "house_id": house_id,
        "task_type": task_type
    })

async def _log_scraping_completion(
    db: Database, 
    house_id: int, 
    task_type: str, 
    status: str,
    items_processed: int = 0,
    items_created: int = 0,
    error_message: Optional[str] = None
):
    """Log the completion of a scraping task"""
    query = """
        INSERT INTO scraping_logs (
            house_id, task_type, status, start_time, end_time,
            items_processed, items_created, error_message
        )
        VALUES (
            :house_id, :task_type, :status, NOW(), NOW(),
            :items_processed, :items_created, :error_message
        )
        ON CONFLICT DO NOTHING
    """
    
    await db.execute(query, {
        "house_id": house_id,
        "task_type": task_type,
        "status": status,
        "items_processed": items_processed,
        "items_created": items_created,
        "error_message": error_message
    })