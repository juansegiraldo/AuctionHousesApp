# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **Auction Houses Database Application** - building the world's most complete database of art auctions with automated scraping and advanced analytics. The project is currently in **Phase 1 MVP development**.

## Architecture & Stack

- **Backend**: FastAPI + PostgreSQL + Redis + Celery
- **Scraping**: Scrapy + Selenium/Playwright + BeautifulSoup
- **Frontend**: Next.js + React (Phase 1 priority)
- **Database**: PostgreSQL with full-text search capabilities
- **Deployment**: Docker + Docker Compose

## Development Commands

### Essential Commands
```bash
# Start all backend services
make up-backend

# View API logs  
make logs-api

# Access database
make db-shell

# Format code
make format

# Health check
make health
```

### Docker Services
- `postgres` - PostgreSQL database (port 5432)
- `redis` - Redis cache/queue (port 6379)  
- `backend` - FastAPI application (port 8000)
- `celery_worker` - Scraping tasks worker
- `celery_beat` - Task scheduler
- `frontend` - Next.js app (port 3000, future)

### API Documentation
- **Swagger UI**: http://localhost:8000/docs
- **Base URL**: http://localhost:8000/api/v1

## Database Schema

Key tables:
- `auction_houses` - Casa de subastas configuration and metadata
- `auctions` - Individual auction events
- `lots` - Art pieces/items being auctioned
- `artists` - Artist information (normalized)
- `categories` - Hierarchical categorization system
- `scraping_logs` - Scraping activity tracking

## Covered Auction Houses (Phase 1 Priority)

**Tier 1 Implementation (MVP):**
- **Bogotá Auctions** (Colombia) - HTML static scraping
- **Durán Subastas** (España) - HTML static scraping
- **Setdart** (España) - HTML + AJAX scraping  
- **Morton Subastas** (México) - HTML static scraping

**Full Coverage (Phase 2):**
- Lefebre Subastas (Colombia) - PDF + Selenium
- Ansorena (España) - HTML + PDF
- Christie's (US) - HTML + JSON APIs
- Sotheby's (US) - HTML + JSON APIs
- Bonhams (UK) - HTML static
- Casa Saráchaga (Argentina) - HTML static

## API Endpoints Structure

### Core Resources
- `/houses/` - Auction house management
- `/auctions/` - Auction listings and details
- `/lots/` - Art lot search and details
- `/artists/` - Artist information and statistics
- `/analytics/` - Market insights and trends

### Common Patterns
- All endpoints support pagination (`limit`, `offset`)
- Search endpoints use full-text search
- Filter parameters available on list endpoints
- Related data included where appropriate

## Scraping Implementation

### Adapter Strategy
Each auction house has a dedicated adapter in `app/scraping/adapters/`:
- `html_static` - Simple requests + BeautifulSoup
- `html_ajax` - Requests with JSON API calls
- `pdf_selenium` - Selenium + PDF parsing
- `html_json` - HTML scraping + embedded JSON

### Task Scheduling
- **Daily scraping**: Major houses (Christie's, Sotheby's, etc.)
- **Weekly scraping**: Regional houses with less frequent updates
- **Celery Beat**: Automated scheduling system

## Development Workflow

1. **Database changes**: Update SQL in `database/migrations/`
2. **API changes**: Update schemas in `app/models/schemas.py`
3. **New endpoints**: Add to appropriate router in `app/api/v1/`
4. **Services**: Business logic in `app/services/`
5. **Scraping**: New adapters in `app/scraping/adapters/`

## Current Implementation Status

✅ **Completed (Phase 1)**:
- Complete project structure
- Docker containerization
- PostgreSQL schema with all tables and indexes
- FastAPI backend with all endpoint definitions
- Pydantic models and validation
- API documentation

🔄 **In Progress**:
- Service layer implementation
- Scraping adapter development  
- Frontend development
- Testing suite

## Testing Strategy

- **Unit tests**: Service layer testing with pytest
- **Integration tests**: API endpoint testing
- **Scraping tests**: Mock adapter testing
- **Load tests**: Performance validation

## Data Sources & Research

The project is based on comprehensive research of 12 major auction houses documented in `auction_houses_research.json`, including:
- Technical scraping strategies for each house
- URL patterns and navigation structures  
- Sample auction and lot data
- Implementation complexity assessments