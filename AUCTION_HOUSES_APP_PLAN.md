# Plan de Desarrollo: Auction Houses Database App

## Visión del Proyecto

Crear la base de datos más completa de subastas de arte del mundo, con scraping automatizado de casas de subastas internacionales y capa analítica avanzada para insights del mercado de arte.

## Arquitectura General

### Microservicios Core

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Scraping  │    │   Data Processing│    │   Analytics     │
│   Service       │───▶│   Service        │───▶│   Service       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Raw Data      │    │   Clean Data    │    │   Analytics     │
│   Storage       │    │   Database      │    │   Database      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Componentes Principales

1. **Scraping Engine**: Sistema distribuido de extracción de datos
2. **Data Processing Pipeline**: Normalización y enriquecimiento de datos  
3. **Core Database**: PostgreSQL con datos estructurados
4. **Analytics Engine**: Procesamiento y análisis de tendencias
5. **REST API**: Endpoints para consultas y analytics
6. **Dashboard Web**: Interface de usuario para visualización

## Esquema de Base de Datos

### Entidades Core

```sql
-- Casas de Subastas
CREATE TABLE auction_houses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(100) NOT NULL,
    website VARCHAR(500) NOT NULL,
    description TEXT,
    scraping_config JSONB,
    last_scrape TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Subastas
CREATE TABLE auctions (
    id SERIAL PRIMARY KEY,
    house_id INTEGER REFERENCES auction_houses(id),
    title VARCHAR(500) NOT NULL,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    status VARCHAR(20) DEFAULT 'upcoming', -- upcoming, active, completed
    location VARCHAR(200),
    auction_type VARCHAR(50), -- live, online, hybrid
    slug VARCHAR(300),
    total_lots INTEGER DEFAULT 0,
    total_value DECIMAL(15,2),
    currency VARCHAR(3) DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Lotes
CREATE TABLE lots (
    id SERIAL PRIMARY KEY,
    auction_id INTEGER REFERENCES auctions(id),
    lot_number VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    artist_id INTEGER REFERENCES artists(id),
    category_id INTEGER REFERENCES categories(id),
    estimated_price_min DECIMAL(12,2),
    estimated_price_max DECIMAL(12,2),
    final_price DECIMAL(12,2),
    currency VARCHAR(3) DEFAULT 'USD',
    sold BOOLEAN DEFAULT FALSE,
    images JSONB,
    dimensions VARCHAR(200),
    provenance TEXT,
    condition_report TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Artistas (normalizado)
CREATE TABLE artists (
    id SERIAL PRIMARY KEY,
    name VARCHAR(300) NOT NULL,
    birth_year INTEGER,
    death_year INTEGER,
    nationality VARCHAR(100),
    movement VARCHAR(100),
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Categorías jerárquicas
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    parent_category_id INTEGER REFERENCES categories(id),
    level INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX idx_auctions_house_date ON auctions(house_id, start_date);
CREATE INDEX idx_lots_auction ON lots(auction_id);
CREATE INDEX idx_lots_artist ON lots(artist_id);
CREATE INDEX idx_lots_price ON lots(final_price DESC);
CREATE INDEX idx_artists_name ON artists(name);
```

## Sistema de Scraping

### Configuración por Casa de Subastas

```python
SCRAPING_CONFIGS = {
    "bogota_auctions": {
        "strategy": "html_static",
        "frequency": "daily",
        "urls": {
            "active": "https://www.bogotaauctions.com/es/subastas-activas",
            "historical": "https://www.bogotaauctions.com/es/subastas-historicas"
        },
        "selectors": {
            "auction_links": "a.titulo-subasta",
            "lots": "div.lote"
        }
    },
    "duran_subastas": {
        "strategy": "html_static", 
        "frequency": "daily",
        "urls": {
            "upcoming": "https://www.duran-subastas.com/subasta-647-julio-2025",
            "historical": "https://www.duran-subastas.com/historico-de-subastas"
        }
    },
    "setdart": {
        "strategy": "html_ajax",
        "frequency": "daily", 
        "urls": {
            "calendar": "https://www.setdart.com/es/subastas/calendario"
        }
    },
    "lefebre": {
        "strategy": "pdf_selenium",
        "frequency": "weekly",
        "urls": {
            "current": "https://lefebresubastas.com/subasta-en-curso/",
            "past": "https://lefebresubastas.com/subastas-anteriores/"
        }
    }
}
```

### Adaptadores por Estrategia

```python
class ScrapingAdapter:
    def __init__(self, config):
        self.config = config
        
    def scrape_auctions(self) -> List[AuctionData]:
        pass
        
    def scrape_lots(self, auction_url: str) -> List[LotData]:
        pass

class HTMLStaticAdapter(ScrapingAdapter):
    def scrape_auctions(self):
        # Implementación con requests + BeautifulSoup
        pass

class HTMLAjaxAdapter(ScrapingAdapter):
    def scrape_auctions(self):
        # Implementación con requests + análisis de JSON
        pass
        
class PDFSeleniumAdapter(ScrapingAdapter):
    def scrape_auctions(self):
        # Implementación con Selenium + PDFMiner
        pass
```

## Stack Tecnológico

### Backend
- **Framework**: FastAPI (Python)
- **Base de datos**: PostgreSQL 15+
- **Cache**: Redis
- **Queue**: Celery + Redis
- **Containerización**: Docker + Docker Compose

### Scraping Engine
- **Framework principal**: Scrapy
- **JavaScript rendering**: Playwright
- **HTML parsing**: BeautifulSoup4
- **PDF processing**: PDFMiner, PyPDF2
- **Data validation**: Pydantic

### Analytics
- **Data processing**: Pandas, NumPy
- **Machine Learning**: Scikit-learn
- **Visualizations**: Plotly
- **Time series**: Prophet (Facebook)

### Frontend
- **Framework**: Next.js (React)
- **UI Components**: Material-UI / Chakra UI
- **Charts**: Chart.js, D3.js
- **Estado**: Zustand / Redux Toolkit

---

# FASE 1: MVP DETALLADO (2-3 meses)

## Objetivo de la Fase 1

Crear un MVP funcional que demuestre la viabilidad técnica del proyecto con:
- Base de datos operativa con 4 casas de subastas
- Sistema de scraping automatizado básico
- API REST funcional
- Dashboard web simple para visualización de datos

## Entregables Específicos

### 1. Infraestructura Base (Semana 1-2)

#### 1.1 Configuración del Entorno
- **Docker Compose** con servicios:
  - PostgreSQL 15
  - Redis 7
  - API Backend (FastAPI)
  - Frontend (Next.js)
  - Celery Worker

#### 1.2 Base de Datos
- **Schema completo** implementado en PostgreSQL
- **Migraciones** con Alembic
- **Datos iniciales**: 12 casas de subastas configuradas
- **Índices de performance** creados

```sql
-- Datos iniciales para MVP
INSERT INTO auction_houses (name, country, website, scraping_config) VALUES
('Bogotá Auctions', 'Colombia', 'https://www.bogotaauctions.com', '{"strategy": "html_static"}'),
('Durán Arte y Subastas', 'España', 'https://www.duran-subastas.com', '{"strategy": "html_static"}'),
('Setdart', 'España', 'https://www.setdart.com', '{"strategy": "html_ajax"}'),
('Morton Subastas', 'México', 'https://www.mortonsubastas.com', '{"strategy": "html_static"}');
```

### 2. Sistema de Scraping MVP (Semana 3-5)

#### 2.1 Implementación de Adaptadores Prioritarios

**Casa 1: Bogotá Auctions (HTML Estático)**
```python
class BogotaAuctionsAdapter(ScrapingAdapter):
    def scrape_auctions(self):
        """Extrae subastas activas e históricas"""
        url = "https://www.bogotaauctions.com/es/subastas-activas"
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        auctions = []
        for link in soup.select('a.titulo-subasta'):
            auction_data = self._parse_auction_page(link['href'])
            auctions.append(auction_data)
        return auctions
    
    def scrape_lots(self, auction_url):
        """Extrae lotes de una subasta específica"""
        response = requests.get(auction_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        lots = []
        for lot_element in soup.select('div.lote'):
            lot_data = {
                'lot_number': lot_element.select_one('span.numero').get_text(strip=True),
                'title': lot_element.select_one('h3').get_text(strip=True),
                'description': lot_element.select_one('.descripcion').get_text(strip=True),
                'estimated_price': self._parse_price(lot_element.select_one('.precio')),
                'images': self._extract_images(lot_element)
            }
            lots.append(lot_data)
        return lots
```

**Casa 2: Durán Subastas (HTML Estático)**
```python
class DuranSubastasAdapter(ScrapingAdapter):
    def scrape_auctions(self):
        """Scraping del histórico paginado"""
        url = 'https://www.duran-subastas.com/historico-de-subastas'
        # Implementación similar con paginación
        pass
```

**Casa 3: Setdart (HTML + AJAX)**
```python
class SetdartAdapter(ScrapingAdapter):
    def scrape_auctions(self):
        """Manejo de calendario con AJAX"""
        calendar_url = 'https://www.setdart.com/es/subastas/calendario'
        # Implementación con requests para JSON endpoints
        pass
```

**Casa 4: Morton Subastas (Live Platform)**
```python
class MortonSubastasAdapter(ScrapingAdapter):
    def scrape_auctions(self):
        """Scraping de live.mortonsubastas.com"""
        url = "https://live.mortonsubastas.com/en/auctions"
        # Implementación básica HTML
        pass
```

#### 2.2 Sistema de Orquestación
```python
class ScrapingOrchestrator:
    def __init__(self):
        self.adapters = {
            'bogota_auctions': BogotaAuctionsAdapter(),
            'duran_subastas': DuranSubastasAdapter(), 
            'setdart': SetdartAdapter(),
            'morton_subastas': MortonSubastasAdapter()
        }
    
    def schedule_scraping_jobs(self):
        """Programa trabajos de scraping con Celery"""
        for house_name, adapter in self.adapters.items():
            scrape_house_data.delay(house_name)
```

#### 2.3 Tareas Celery
```python
@celery.task
def scrape_house_data(house_name: str):
    """Tarea asíncrona de scraping"""
    adapter = get_adapter(house_name)
    
    try:
        # Scraping de subastas
        auctions = adapter.scrape_auctions()
        
        for auction_data in auctions:
            # Guardar subasta en BD
            auction = save_auction(auction_data)
            
            # Scraping de lotes
            lots = adapter.scrape_lots(auction_data['url'])
            save_lots(auction.id, lots)
            
        log_scraping_success(house_name)
        
    except Exception as e:
        log_scraping_error(house_name, str(e))
```

### 3. API Backend (Semana 4-6)

#### 3.1 Modelos Pydantic
```python
class AuctionHouse(BaseModel):
    id: int
    name: str
    country: str
    website: str
    total_auctions: int
    last_scrape: Optional[datetime]

class Auction(BaseModel):
    id: int
    house_id: int
    house_name: str
    title: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    status: str
    location: Optional[str]
    total_lots: int
    total_value: Optional[Decimal]

class Lot(BaseModel):
    id: int
    auction_id: int
    lot_number: str
    title: str
    artist_name: Optional[str]
    category: Optional[str]
    estimated_price_min: Optional[Decimal]
    estimated_price_max: Optional[Decimal]
    final_price: Optional[Decimal]
    sold: bool
    images: List[str]
```

#### 3.2 Endpoints Core
```python
from fastapi import FastAPI, Depends, Query
from typing import List, Optional

app = FastAPI(title="Auction Houses API", version="1.0.0")

@app.get("/houses/", response_model=List[AuctionHouse])
async def get_auction_houses():
    """Lista todas las casas de subastas"""
    return await AuctionHouseService.get_all()

@app.get("/auctions/", response_model=List[Auction])
async def get_auctions(
    house_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100)
):
    """Lista subastas con filtros"""
    return await AuctionService.get_auctions(house_id, status, limit)

@app.get("/auctions/{auction_id}/lots/", response_model=List[Lot])
async def get_auction_lots(auction_id: int):
    """Obtiene lotes de una subasta específica"""
    return await LotService.get_by_auction(auction_id)

@app.get("/lots/search/", response_model=List[Lot])
async def search_lots(
    q: str = Query(..., min_length=3),
    artist: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    price_min: Optional[int] = Query(None),
    price_max: Optional[int] = Query(None)
):
    """Búsqueda avanzada de lotes"""
    return await LotService.search(q, artist, category, price_min, price_max)

@app.get("/stats/summary/")
async def get_summary_stats():
    """Estadísticas generales del sistema"""
    return {
        "total_houses": await AuctionHouseService.count(),
        "total_auctions": await AuctionService.count(),
        "total_lots": await LotService.count(),
        "total_value": await LotService.total_value(),
        "last_update": await SystemService.last_scrape_time()
    }
```

### 4. Dashboard Web MVP (Semana 6-8)

#### 4.1 Páginas Principales

**Página Principal - Overview**
```tsx
// pages/index.tsx
import { useEffect, useState } from 'react';
import { Grid, Paper, Typography, Card } from '@mui/material';

export default function Dashboard() {
    const [stats, setStats] = useState(null);
    
    useEffect(() => {
        fetch('/api/stats/summary/')
            .then(res => res.json())
            .then(setStats);
    }, []);
    
    return (
        <Grid container spacing={3}>
            <Grid item xs={12} md={3}>
                <StatsCard 
                    title="Casas de Subastas" 
                    value={stats?.total_houses}
                    icon="🏛️"
                />
            </Grid>
            <Grid item xs={12} md={3}>
                <StatsCard 
                    title="Subastas Totales" 
                    value={stats?.total_auctions}
                    icon="🔨"
                />
            </Grid>
            <Grid item xs={12} md={3}>
                <StatsCard 
                    title="Lotes Registrados" 
                    value={stats?.total_lots}
                    icon="🎨"
                />
            </Grid>
            <Grid item xs={12} md={3}>
                <StatsCard 
                    title="Valor Total" 
                    value={stats?.total_value}
                    format="currency"
                    icon="💰"
                />
            </Grid>
        </Grid>
    );
}
```

**Página de Casas de Subastas**
```tsx
// pages/houses.tsx
export default function AuctionHouses() {
    const [houses, setHouses] = useState([]);
    
    return (
        <Grid container spacing={2}>
            {houses.map(house => (
                <Grid item xs={12} md={6} lg={4} key={house.id}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6">{house.name}</Typography>
                            <Typography color="textSecondary">{house.country}</Typography>
                            <Typography variant="body2">
                                {house.total_auctions} subastas registradas
                            </Typography>
                            <Button 
                                variant="outlined" 
                                href={`/houses/${house.id}`}
                            >
                                Ver Subastas
                            </Button>
                        </CardContent>
                    </Card>
                </Grid>
            ))}
        </Grid>
    );
}
```

**Página de Subastas**
```tsx
// pages/auctions.tsx
import { DataGrid } from '@mui/x-data-grid';

export default function AuctionsPage() {
    const columns = [
        { field: 'title', headerName: 'Título', width: 300 },
        { field: 'house_name', headerName: 'Casa', width: 200 },
        { field: 'start_date', headerName: 'Fecha Inicio', width: 150, type: 'date' },
        { field: 'status', headerName: 'Estado', width: 120 },
        { field: 'total_lots', headerName: 'Lotes', width: 100, type: 'number' },
        { field: 'total_value', headerName: 'Valor', width: 150, type: 'number' }
    ];
    
    return (
        <Paper sx={{ height: 600, width: '100%' }}>
            <DataGrid
                rows={auctions}
                columns={columns}
                pageSize={25}
                checkboxSelection
                disableSelectionOnClick
            />
        </Paper>
    );
}
```

#### 4.2 Componentes de Visualización

**Gráfico de Tendencias**
```tsx
// components/TrendsChart.tsx
import { Line } from 'react-chartjs-2';

export function TrendsChart({ data }) {
    const chartData = {
        labels: data.dates,
        datasets: [
            {
                label: 'Valor Total de Subastas',
                data: data.values,
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
            }
        ]
    };
    
    return <Line data={chartData} options={{ responsive: true }} />;
}
```

### 5. Monitoreo y Logging (Semana 7-8)

#### 5.1 Sistema de Logs
```python
import logging
from pythonjsonlogger import jsonlogger

# Configuración de logging estructurado
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger = logging.getLogger()
logger.addHandler(logHandler)

class ScrapingLogger:
    @staticmethod
    def log_scraping_start(house_name: str):
        logger.info("Scraping started", extra={
            "event": "scraping_start",
            "house": house_name,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    @staticmethod
    def log_scraping_success(house_name: str, auctions_count: int, lots_count: int):
        logger.info("Scraping completed successfully", extra={
            "event": "scraping_success", 
            "house": house_name,
            "auctions_scraped": auctions_count,
            "lots_scraped": lots_count
        })
```

#### 5.2 Health Checks
```python
@app.get("/health/")
async def health_check():
    """Endpoint de health check"""
    return {
        "status": "healthy",
        "database": await check_database_connection(),
        "redis": await check_redis_connection(),
        "last_scrape": await get_last_scrape_time()
    }
```

## Cronograma Detallado - Fase 1

### **Semana 1-2: Infraestructura Base**
- **Días 1-3**: Configuración Docker Compose, PostgreSQL, Redis
- **Días 4-7**: Esquema de base de datos, migraciones, datos iniciales  
- **Días 8-10**: Setup FastAPI, estructura del proyecto, configuración

### **Semana 3-4: Adaptadores de Scraping**
- **Días 11-14**: Implementación adaptador Bogotá Auctions
- **Días 15-18**: Implementación adaptador Durán Subastas  
- **Días 19-21**: Testing y refinamiento de adaptadores

### **Semana 5-6: Sistema de Orquestación**
- **Días 22-25**: Configuración Celery, tareas asíncronas
- **Días 26-28**: Implementación Setdart y Morton adaptadores
- **Días 29-32**: Sistema de scheduling, manejo de errores

### **Semana 7-8: API Backend**
- **Días 33-36**: Implementación endpoints core
- **Días 37-39**: Servicios de búsqueda y filtrado
- **Días 40-42**: Testing API, documentación

### **Semana 9-10: Frontend MVP**
- **Días 43-46**: Setup Next.js, páginas principales
- **Días 47-49**: Componentes de visualización
- **Días 50-52**: Integración con API, testing

### **Semana 11-12: Refinamiento y Deploy**
- **Días 53-56**: Testing integral, corrección de bugs
- **Días 57-59**: Optimización de performance
- **Días 60-63**: Deploy en ambiente de producción, monitoreo

## Criterios de Éxito - Fase 1

### Métricas Técnicas
- **Coverage de datos**: Al menos 100 subastas y 1000 lotes por casa
- **Uptime del scraping**: 95% de trabajos completados exitosamente  
- **API performance**: Respuesta promedio < 200ms
- **Frontend usability**: Carga de páginas < 3 segundos

### Funcionalidades Validadas
- ✅ Scraping automatizado funcionando para 4 casas
- ✅ Base de datos poblada con datos reales
- ✅ API REST completamente funcional
- ✅ Dashboard web navegable y responsive
- ✅ Sistema de monitoreo operativo

### Entregables Finales
1. **Código fuente**: Repositorio Git organizado
2. **Base de datos**: Schema productivo con datos reales
3. **API documentada**: OpenAPI/Swagger completo
4. **Frontend funcional**: Dashboard web responsive  
5. **Documentación**: Guías de instalación y uso
6. **Deploy**: Ambiente de producción funcionando

## Consideraciones de Escalabilidad

### Preparación para Fase 2
- **Arquitectura modular**: Fácil adición de nuevos adaptadores
- **Base de datos optimizada**: Índices para crecimiento de datos
- **API versionada**: Endpoints preparados para evolución
- **Monitoreo**: Métricas base para optimización futura

Esta Fase 1 establecerá las bases sólidas para el crecimiento del proyecto hacia una plataforma completa de análisis del mercado de arte global.