from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

class AuctionData:
    """Data structure for scraped auction information"""
    def __init__(self, **kwargs):
        self.title: str = kwargs.get('title', '')
        self.description: Optional[str] = kwargs.get('description')
        self.start_date: Optional[datetime] = kwargs.get('start_date')
        self.end_date: Optional[datetime] = kwargs.get('end_date')
        self.location: Optional[str] = kwargs.get('location')
        self.auction_type: str = kwargs.get('auction_type', 'live')
        self.slug: Optional[str] = kwargs.get('slug')
        self.external_id: Optional[str] = kwargs.get('external_id')
        self.external_url: Optional[str] = kwargs.get('external_url')
        self.status: str = kwargs.get('status', 'upcoming')

class LotData:
    """Data structure for scraped lot information"""
    def __init__(self, **kwargs):
        self.lot_number: str = kwargs.get('lot_number', '')
        self.title: str = kwargs.get('title', '')
        self.description: Optional[str] = kwargs.get('description')
        self.artist_name: Optional[str] = kwargs.get('artist_name')
        self.category: Optional[str] = kwargs.get('category')
        self.estimated_price_min: Optional[float] = kwargs.get('estimated_price_min')
        self.estimated_price_max: Optional[float] = kwargs.get('estimated_price_max')
        self.final_price: Optional[float] = kwargs.get('final_price')
        self.sold: bool = kwargs.get('sold', False)
        self.currency: str = kwargs.get('currency', 'USD')
        self.images: List[str] = kwargs.get('images', [])
        self.dimensions: Optional[str] = kwargs.get('dimensions')
        self.medium: Optional[str] = kwargs.get('medium')
        self.external_id: Optional[str] = kwargs.get('external_id')
        self.external_url: Optional[str] = kwargs.get('external_url')

class BaseScrapingAdapter(ABC):
    """Base class for all scraping adapters"""
    
    def __init__(self, house_config: Dict[str, Any]):
        self.house_config = house_config
        self.session = self._create_session()
        self.name = self.__class__.__name__
        
    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry strategy and appropriate headers"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set headers
        session.headers.update({
            'User-Agent': settings.SCRAPING_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
        return session
    
    def _make_request(self, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with rate limiting and error handling"""
        try:
            # Rate limiting
            time.sleep(settings.SCRAPING_DELAY)
            
            # Make request
            response = self.session.get(url, timeout=settings.SCRAPING_TIMEOUT, **kwargs)
            response.raise_for_status()
            
            logger.debug(f"Successfully fetched {url}")
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            raise
    
    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text, handling different formats"""
        if not price_text:
            return None
            
        # Remove common currency symbols and separators
        clean_price = price_text.replace('$', '').replace('€', '').replace('£', '')
        clean_price = clean_price.replace(',', '').replace('.', '', clean_price.count('.') - 1)
        clean_price = clean_price.strip()
        
        try:
            return float(clean_price)
        except ValueError:
            logger.warning(f"Could not parse price: {price_text}")
            return None
    
    def _parse_date(self, date_text: str, date_format: str = None) -> Optional[datetime]:
        """Parse date from text"""
        if not date_text:
            return None
            
        # Common date formats to try
        formats = [
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%d/%m/%Y %H:%M',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%B %d, %Y',
            '%d %B %Y'
        ]
        
        if date_format:
            formats.insert(0, date_format)
        
        for fmt in formats:
            try:
                return datetime.strptime(date_text.strip(), fmt)
            except ValueError:
                continue
                
        logger.warning(f"Could not parse date: {date_text}")
        return None
    
    def _extract_images(self, element) -> List[str]:
        """Extract image URLs from HTML element"""
        images = []
        
        # Find img tags
        img_tags = element.find_all('img') if hasattr(element, 'find_all') else []
        
        for img in img_tags:
            src = img.get('src') or img.get('data-src')
            if src:
                # Convert relative URLs to absolute
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    base_url = self.house_config.get('urls', {}).get('base', '')
                    if base_url:
                        src = base_url.rstrip('/') + src
                        
                images.append(src)
        
        return images
    
    @abstractmethod
    async def scrape_auctions(self) -> List[AuctionData]:
        """Scrape auction listings from the house's website"""
        pass
    
    @abstractmethod 
    async def scrape_lots(self, auction_data: AuctionData) -> List[LotData]:
        """Scrape lot details for a specific auction"""
        pass
    
    def get_scraping_stats(self) -> Dict[str, Any]:
        """Get statistics about the scraping session"""
        return {
            "adapter_name": self.name,
            "house_name": self.house_config.get('name', 'Unknown'),
            "strategy": self.house_config.get('strategy', 'unknown'),
            "timestamp": datetime.utcnow().isoformat()
        }