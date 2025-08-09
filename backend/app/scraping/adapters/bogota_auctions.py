from typing import List, Optional
from bs4 import BeautifulSoup
import re
import logging

from app.scraping.base_adapter import BaseScrapingAdapter, AuctionData, LotData

logger = logging.getLogger(__name__)

class BogotaAuctionsAdapter(BaseScrapingAdapter):
    """
    Scraping adapter for Bogotá Auctions (Colombia)
    Website: https://www.bogotaauctions.com
    Strategy: HTML static scraping with BeautifulSoup
    """
    
    def __init__(self, house_config):
        super().__init__(house_config)
        self.base_url = "https://www.bogotaauctions.com"
        
    async def scrape_auctions(self) -> List[AuctionData]:
        """Scrape auction listings from active and historical pages"""
        auctions = []
        
        # Scrape active auctions
        active_auctions = await self._scrape_active_auctions()
        auctions.extend(active_auctions)
        
        # Scrape historical auctions  
        historical_auctions = await self._scrape_historical_auctions()
        auctions.extend(historical_auctions)
        
        logger.info(f"Scraped {len(auctions)} auctions from Bogotá Auctions")
        return auctions
    
    async def _scrape_active_auctions(self) -> List[AuctionData]:
        """Scrape active auctions page"""
        url = f"{self.base_url}/es/subastas-activas"
        auctions = []
        
        try:
            response = self._make_request(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find auction links based on the research pattern
            auction_links = soup.select('a.titulo-subasta')
            
            for link in auction_links:
                auction_data = await self._parse_auction_from_link(link, status='active')
                if auction_data:
                    auctions.append(auction_data)
                    
        except Exception as e:
            logger.error(f"Error scraping active auctions from Bogotá Auctions: {e}")
        
        return auctions
    
    async def _scrape_historical_auctions(self) -> List[AuctionData]:
        """Scrape historical auctions page"""
        url = f"{self.base_url}/es/subastas-historicas"
        auctions = []
        
        try:
            response = self._make_request(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find auction links
            auction_links = soup.select('a.titulo-subasta, a[href*="subasta"]')
            
            for link in auction_links:
                auction_data = await self._parse_auction_from_link(link, status='completed')
                if auction_data:
                    auctions.append(auction_data)
                    
        except Exception as e:
            logger.error(f"Error scraping historical auctions from Bogotá Auctions: {e}")
        
        return auctions
    
    async def _parse_auction_from_link(self, link_element, status: str = 'upcoming') -> Optional[AuctionData]:
        """Parse auction data from a link element and its detail page"""
        try:
            # Get auction URL
            href = link_element.get('href')
            if not href:
                return None
            
            # Convert relative URL to absolute
            if href.startswith('/'):
                auction_url = f"{self.base_url}{href}"
            else:
                auction_url = href
            
            # Get basic info from link text
            title = link_element.get_text(strip=True)
            if not title:
                return None
            
            # Extract slug and external_id from URL
            slug = href.split('/')[-1] if '/' in href else href
            external_id = self._extract_external_id_from_url(href)
            
            # Visit auction detail page for more information
            auction_details = await self._get_auction_details(auction_url)
            
            return AuctionData(
                title=title,
                description=auction_details.get('description'),
                start_date=auction_details.get('start_date'),
                end_date=auction_details.get('end_date'),
                location=auction_details.get('location', 'Bogotá, Colombia'),
                auction_type=auction_details.get('auction_type', 'hybrid'),
                slug=slug,
                external_id=external_id,
                external_url=auction_url,
                status=status
            )
            
        except Exception as e:
            logger.error(f"Error parsing auction from link: {e}")
            return None
    
    async def _get_auction_details(self, auction_url: str) -> dict:
        """Get detailed information from auction page"""
        details = {}
        
        try:
            response = self._make_request(auction_url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract description
            description_elem = soup.find('div', class_='descripcion-subasta') or soup.find('div', class_='description')
            if description_elem:
                details['description'] = description_elem.get_text(strip=True)
            
            # Extract dates - look for date patterns in text
            date_text = soup.get_text()
            dates = self._extract_dates_from_text(date_text)
            if dates:
                details['start_date'] = dates.get('start_date')
                details['end_date'] = dates.get('end_date')
            
            # Extract location
            location_elem = soup.find(text=re.compile(r'Bogotá|Colombia|Lugar|Location'))
            if location_elem:
                details['location'] = 'Bogotá, Colombia'
            
            # Determine auction type based on content
            content_text = soup.get_text().lower()
            if 'virtual' in content_text or 'online' in content_text:
                details['auction_type'] = 'online'
            elif 'presencial' in content_text or 'live' in content_text:
                details['auction_type'] = 'live'  
            else:
                details['auction_type'] = 'hybrid'
                
        except Exception as e:
            logger.error(f"Error getting auction details from {auction_url}: {e}")
        
        return details
    
    async def scrape_lots(self, auction_data: AuctionData) -> List[LotData]:
        """Scrape lot details for a specific auction"""
        if not auction_data.external_url:
            logger.warning(f"No external URL for auction: {auction_data.title}")
            return []
        
        lots = []
        
        try:
            response = self._make_request(auction_data.external_url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find lots based on research pattern - look for div.lote
            lot_elements = soup.select('div.lote')
            
            for lot_elem in lot_elements:
                lot_data = self._parse_lot_element(lot_elem, auction_data)
                if lot_data:
                    lots.append(lot_data)
            
            # If no lots found with primary selector, try alternative selectors
            if not lots:
                alternative_selectors = [
                    'div[class*="lot"]',
                    'div[class*="item"]', 
                    'article',
                    '.auction-lot'
                ]
                
                for selector in alternative_selectors:
                    lot_elements = soup.select(selector)
                    if lot_elements:
                        logger.info(f"Found lots with alternative selector: {selector}")
                        for lot_elem in lot_elements:
                            lot_data = self._parse_lot_element(lot_elem, auction_data)
                            if lot_data:
                                lots.append(lot_data)
                        break
            
            logger.info(f"Scraped {len(lots)} lots from auction: {auction_data.title}")
            
        except Exception as e:
            logger.error(f"Error scraping lots from {auction_data.external_url}: {e}")
        
        return lots
    
    def _parse_lot_element(self, lot_element, auction_data: AuctionData) -> Optional[LotData]:
        """Parse individual lot from HTML element"""
        try:
            # Extract lot number
            lot_number_elem = lot_element.select_one('span.numero, .lot-number, [class*="number"]')
            lot_number = lot_number_elem.get_text(strip=True) if lot_number_elem else "N/A"
            
            # Extract title
            title_elem = lot_element.select_one('h3, h2, .title, [class*="title"]')
            title = title_elem.get_text(strip=True) if title_elem else "Sin título"
            
            if not title or title == "Sin título":
                return None
            
            # Extract description
            desc_elem = lot_element.select_one('.descripcion, .description, p')
            description = desc_elem.get_text(strip=True) if desc_elem else None
            
            # Extract artist name
            artist_name = self._extract_artist_from_text(f"{title} {description or ''}")
            
            # Extract price information
            price_elem = lot_element.select_one('.precio, .price, [class*="price"]')
            price_info = self._parse_price_info(price_elem.get_text() if price_elem else "")
            
            # Extract images
            images = self._extract_images(lot_element)
            
            # Extract additional details
            details = self._extract_lot_details(lot_element)
            
            return LotData(
                lot_number=lot_number,
                title=title,
                description=description,
                artist_name=artist_name,
                category=details.get('category'),
                estimated_price_min=price_info.get('min_price'),
                estimated_price_max=price_info.get('max_price'),
                final_price=price_info.get('final_price'),
                sold=price_info.get('sold', False),
                currency='COP',  # Colombian Pesos for Bogotá Auctions
                images=images,
                dimensions=details.get('dimensions'),
                medium=details.get('medium'),
                external_id=f"{auction_data.external_id}_{lot_number}" if auction_data.external_id else None
            )
            
        except Exception as e:
            logger.error(f"Error parsing lot element: {e}")
            return None
    
    def _extract_external_id_from_url(self, url: str) -> Optional[str]:
        """Extract external ID from URL"""
        # Try to extract ID from URL patterns
        patterns = [
            r'/subasta/(\d+)',
            r'/(\d+)',
            r'id=(\d+)',
            r'subasta-(\w+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_dates_from_text(self, text: str) -> dict:
        """Extract start and end dates from text content"""
        dates = {}
        
        # Spanish date patterns
        date_patterns = [
            r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s+(\d{1,2}):(\d{2})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})',
            r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})'
        ]
        
        spanish_months = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
            'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
            'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
        }
        
        for pattern in date_patterns:
            matches = re.finditer(pattern, text.lower())
            for match in matches:
                groups = match.groups()
                try:
                    if len(groups) == 5:  # day, month, year, hour, minute
                        day, month, year, hour, minute = groups
                        if month in spanish_months:
                            month_num = spanish_months[month]
                        else:
                            month_num = int(month)
                        
                        date_obj = self._parse_date(f"{year}-{month_num:02d}-{int(day):02d} {hour}:{minute}")
                        if date_obj:
                            if 'start_date' not in dates:
                                dates['start_date'] = date_obj
                            else:
                                dates['end_date'] = date_obj
                except:
                    continue
        
        return dates
    
    def _extract_artist_from_text(self, text: str) -> Optional[str]:
        """Extract artist name from title/description text"""
        # Common patterns for artist names in Spanish auction text
        patterns = [
            r'por\s+([A-Z][a-záéíóúñü]+(?:\s+[A-Z][a-záéíóúñü]+)*)',
            r'de\s+([A-Z][a-záéíóúñü]+(?:\s+[A-Z][a-záéíóúñü]+)*)',
            r'([A-Z][a-záéíóúñü]+,\s+[A-Z][a-záéíóúñü]+)',
            r'([A-Z][A-Z\s]+)\s*\('
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                artist = match.group(1).strip()
                # Filter out common non-artist words
                if len(artist) > 3 and artist.lower() not in ['obra', 'pieza', 'sin', 'título']:
                    return artist
        
        return None
    
    def _parse_price_info(self, price_text: str) -> dict:
        """Parse price information from text"""
        price_info = {}
        
        if not price_text:
            return price_info
        
        # Remove currency symbols and normalize
        clean_text = price_text.replace('$', '').replace('.', '').replace(',', '')
        
        # Look for price ranges (e.g., "100000 - 150000")
        range_match = re.search(r'(\d+)\s*[-–]\s*(\d+)', clean_text)
        if range_match:
            price_info['min_price'] = float(range_match.group(1))
            price_info['max_price'] = float(range_match.group(2))
        else:
            # Look for single price
            price_match = re.search(r'(\d+)', clean_text)
            if price_match:
                price = float(price_match.group(1))
                price_info['min_price'] = price
                price_info['max_price'] = price
        
        # Check if sold
        if 'vendido' in price_text.lower() or 'sold' in price_text.lower():
            price_info['sold'] = True
            price_info['final_price'] = price_info.get('max_price')
        
        return price_info
    
    def _extract_lot_details(self, lot_element) -> dict:
        """Extract additional lot details like dimensions, medium, etc."""
        details = {}
        
        # Get all text from element
        text = lot_element.get_text()
        
        # Extract dimensions (various patterns)
        dim_patterns = [
            r'(\d+\s*x\s*\d+(?:\s*x\s*\d+)?)\s*cm',
            r'(\d+\s*×\s*\d+(?:\s*×\s*\d+)?)\s*cm',
            r'Dimensiones?:\s*([^,\n]+)'
        ]
        
        for pattern in dim_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                details['dimensions'] = match.group(1).strip()
                break
        
        # Extract medium/technique
        medium_keywords = ['óleo', 'acuarela', 'gouache', 'tinta', 'lápiz', 'carboncillo', 'mixta', 'collage']
        for keyword in medium_keywords:
            if keyword in text.lower():
                details['medium'] = keyword.capitalize()
                break
        
        # Try to determine category from text
        if 'pintura' in text.lower():
            details['category'] = 'Pintura'
        elif 'grabado' in text.lower():
            details['category'] = 'Grabado'
        elif 'escultura' in text.lower():
            details['category'] = 'Escultura'
        elif 'fotografía' in text.lower():
            details['category'] = 'Fotografía'
        
        return details