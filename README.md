# Auction Houses Database Application

La base de datos más completa de subastas de arte del mundo, con scraping automatizado y analytics avanzados.

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)

### Development Setup

1. **Clone and setup environment**
```bash
git clone <repository-url>
cd AuctionHousesApp
cp .env.example .env
```

2. **Start services with Docker**
```bash
# Start all services
docker-compose up -d

# Start without frontend (for backend-only development)
docker-compose up -d postgres redis backend celery_worker celery_beat
```

3. **Access the application**
- **API Documentation**: http://localhost:8000/docs
- **API Base**: http://localhost:8000/api/v1
- **Frontend** (when enabled): http://localhost:3000

### Database Setup

The database will be automatically initialized with:
- Schema creation (tables, indexes, triggers)
- Initial auction houses data
- Sample categories and artists

## 📊 Current Status - Phase 1 MVP

### ✅ Completed (Phase 1 MVP)
- [x] Complete project structure and Docker setup
- [x] PostgreSQL database with full schema, indexes, and triggers  
- [x] FastAPI backend with 27 endpoints across 5 routers
- [x] Complete Service Layer with business logic (5 services)
- [x] Pydantic models with validation (25+ schemas)
- [x] Scraping system with base adapter and Bogotá Auctions implementation
- [x] Celery task system for automated scraping
- [x] Complete API documentation with Swagger
- [x] Testing scripts and development tools
- [x] Makefile with 20+ development commands

### 🎯 Ready for Use
- API is fully functional with all CRUD operations
- Database seeded with 12 auction houses and sample data
- Automated testing suite for all endpoints
- Production-ready Docker containerization

### 📋 API Endpoints

#### Auction Houses
- `GET /api/v1/houses/` - List auction houses
- `GET /api/v1/houses/{id}` - Get house details
- `GET /api/v1/houses/{id}/auctions/` - Get house auctions
- `GET /api/v1/houses/{id}/stats/` - Get house statistics

#### Auctions  
- `GET /api/v1/auctions/` - List auctions (with filters)
- `GET /api/v1/auctions/{id}` - Get auction details
- `GET /api/v1/auctions/{id}/lots/` - Get auction lots
- `GET /api/v1/auctions/{id}/stats/` - Get auction statistics

#### Lots
- `GET /api/v1/lots/` - List lots (with filters)
- `GET /api/v1/lots/search/` - Full-text search lots
- `GET /api/v1/lots/{id}` - Get lot details
- `GET /api/v1/lots/similar/{id}/` - Get similar lots

#### Artists
- `GET /api/v1/artists/` - List artists
- `GET /api/v1/artists/search/` - Search artists
- `GET /api/v1/artists/{id}` - Get artist details
- `GET /api/v1/artists/{id}/lots/` - Get artist lots
- `GET /api/v1/artists/{id}/stats/` - Get artist statistics

#### Analytics
- `GET /api/v1/analytics/summary/` - Summary statistics
- `GET /api/v1/analytics/trends/prices/` - Price trends
- `GET /api/v1/analytics/trends/volume/` - Volume trends
- `GET /api/v1/analytics/top-artists/` - Top artists
- `GET /api/v1/analytics/market-insights/` - Market insights

## 🏛️ Covered Auction Houses

### Phase 1 Priority (4 houses)
- **Bogotá Auctions** (Colombia) - HTML Static
- **Durán Subastas** (España) - HTML Static  
- **Setdart** (España) - HTML + AJAX
- **Morton Subastas** (México) - HTML Static

### Full Coverage (12 houses)
- Lefebre Subastas (Colombia)
- Ansorena (España)
- Christie's (Estados Unidos)
- Sotheby's (Estados Unidos)
- Bonhams (Reino Unido)
- Casa Saráchaga (Argentina)

## 🛠️ Development Commands

```bash
# View logs
docker-compose logs -f backend

# Run database migrations
docker-compose exec backend alembic upgrade head

# Access database
docker-compose exec postgres psql -U auction_user -d auction_houses

# Essential commands
make up-backend          # Start all backend services
make logs-api           # View API logs
make test-api          # Test all API endpoints
make populate-test-data # Add sample data

# Database operations
make db-shell          # Access PostgreSQL shell
make db-reset         # Reset database (WARNING: deletes data)

# Code quality
make format           # Format Python code
make lint            # Run code linting

# Monitoring
make status          # Check service status
make health         # Check API health
make logs           # View all service logs

# Cleanup
make down           # Stop all services
make clean         # Remove containers and volumes
```

## 📁 Project Structure

```
AuctionHousesApp/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # API endpoints
│   │   ├── core/            # Configuration, database
│   │   ├── models/          # Pydantic schemas  
│   │   ├── services/        # Business logic
│   │   ├── scraping/        # Scraping adapters
│   │   └── main.py          # FastAPI application
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                # Next.js application (TBD)
├── database/
│   ├── migrations/          # SQL schema files
│   └── seeds/              # Initial data
├── docker-compose.yml
└── docs/                   # Documentation
```

## 🔧 Architecture

- **Backend**: FastAPI + PostgreSQL + Redis
- **Scraping**: Celery + Scrapy + Selenium/Playwright  
- **Frontend**: Next.js + React
- **Database**: PostgreSQL with full-text search
- **Cache/Queue**: Redis
- **Deployment**: Docker containers

## 📈 Roadmap

### Phase 2 (3-4 months)
- Complete scraping system for all 12 houses
- Advanced search and filtering
- Real-time auction updates
- Performance optimization

### Phase 3 (4-6 months)  
- Machine learning price predictions
- Market analysis dashboard
- Public API with authentication
- Mobile application

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`  
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.