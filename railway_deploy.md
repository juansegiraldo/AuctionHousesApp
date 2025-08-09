# 🚂 Deploy en Railway - Guía Paso a Paso

## 📋 Paso 1: Preparar el Proyecto para Railway

Necesitamos crear algunos archivos específicos para Railway:

### 1.1 Crear requirements.txt en la raíz
```bash
# En la carpeta raíz del proyecto, crear requirements.txt
```

### 1.2 Crear railway.toml
```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

### 1.3 Crear Procfile (alternativa)
```
web: python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend
```

### 1.4 Actualizar requirements.txt para Railway
```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
asyncpg==0.29.0
psycopg2-binary==2.9.9
databases==0.8.0
pydantic==2.5.1
pydantic-settings==2.1.0
requests==2.31.0
beautifulsoup4==4.12.2
python-dotenv==1.0.0
```

## 📋 Paso 2: Subir Código a GitHub

```bash
# En tu terminal, desde la carpeta del proyecto:

# 1. Inicializar git (si no está inicializado)
git init

# 2. Añadir el remote (tu repo)
git remote add origin https://github.com/juansegiraldo/AuctionHousesApp.git

# 3. Añadir todos los archivos
git add .

# 4. Hacer commit
git commit -m "Initial commit - Auction Houses Database API"

# 5. Subir a GitHub
git push -u origin main
```

## 📋 Paso 3: Deploy en Railway

### 3.1 Ir a Railway
1. Ve a [railway.app](https://railway.app)
2. Haz clic en "Start a New Project"
3. Conecta tu cuenta de GitHub si no lo has hecho

### 3.2 Crear Proyecto
1. Selecciona "Deploy from GitHub repo"
2. Busca y selecciona `juansegiraldo/AuctionHousesApp`
3. Railway detectará automáticamente que es un proyecto Python

### 3.3 Configurar Base de Datos
1. En el dashboard del proyecto, haz clic en "+ New"
2. Selecciona "Database" → "PostgreSQL" 
3. Railway creará una base de datos PostgreSQL automáticamente

### 3.4 Configurar Variables de Entorno
En la pestaña "Variables" de tu servicio, añadir:

```bash
DATABASE_URL=postgresql://postgres:password@hostname:port/database
ENVIRONMENT=production
SECRET_KEY=railway-production-secret-key-change-me
SCRAPING_ENABLED=true
ALLOWED_HOSTS=*
```

**Nota:** Railway automáticamente generará DATABASE_URL cuando conectes la BD PostgreSQL.

## 📋 Paso 4: Configurar Aplicación para Railway

### 4.1 Actualizar main.py para Railway
Crear archivo `backend/app/railway.py`:

```python
import os
from app.main import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

### 4.2 Configuración de Base de Datos
Railway automáticamente proporcionará la DATABASE_URL. Nuestro código ya está configurado para usarla.

## 📋 Paso 5: Inicializar Base de Datos

### 5.1 Crear script de inicialización
Crear archivo `scripts/railway_init.py`:

```python
#!/usr/bin/env python3
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.core.database import database
from sqlalchemy import text

async def init_railway_db():
    """Initialize Railway database"""
    try:
        await database.connect()
        
        # Read and execute migration files
        migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'database', 'migrations')
        
        # Execute schema
        with open(os.path.join(migrations_dir, '001_initial_schema.sql'), 'r') as f:
            schema_sql = f.read()
        
        # Split by statements and execute
        statements = schema_sql.split(';')
        for statement in statements:
            if statement.strip():
                await database.execute(text(statement))
        
        # Execute seed data
        with open(os.path.join(migrations_dir, '..', 'seeds', '002_auction_houses_data.sql'), 'r') as f:
            seed_sql = f.read()
        
        statements = seed_sql.split(';')
        for statement in statements:
            if statement.strip():
                await database.execute(text(statement))
        
        print("✅ Railway database initialized successfully")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
    finally:
        await database.disconnect()

if __name__ == "__main__":
    asyncio.run(init_railway_db())
```

## 📋 Paso 6: Comandos Git para Actualizar

```bash
# Crear los archivos necesarios primero, luego:

git add .
git commit -m "Add Railway configuration"
git push origin main
```

## 📋 Paso 7: Monitorear Deploy

1. En Railway, ve a la pestaña "Deployments"
2. Verás el progreso del build en tiempo real
3. Cuando termine, tendrás una URL pública tipo: `https://tu-proyecto.up.railway.app`

## 🎉 Paso 8: Probar la API

Una vez deployado:

1. **API Docs**: `https://tu-url.railway.app/docs`
2. **Health Check**: `https://tu-url.railway.app/health`
3. **API Base**: `https://tu-url.railway.app/api/v1`

## 🔧 Troubleshooting

### Si el build falla:
1. Revisa los logs en Railway
2. Asegúrate que requirements.txt esté en la raíz
3. Verifica que el startCommand sea correcto

### Si la base de datos no funciona:
1. Conecta explícitamente la BD PostgreSQL en Railway
2. Verifica que DATABASE_URL esté configurada
3. Ejecuta las migraciones manualmente si es necesario

### Para ver logs:
1. En Railway, pestaña "Deploy Logs"
2. En tiempo real para debugging

## 💡 Tips

1. **Railway es gratis** hasta $5/mes de uso
2. **Auto-deploy**: Cada push a main hace redeploy automático  
3. **Escalable**: Fácil upgrade a plan pagado si necesitas más recursos
4. **Custom domains**: Puedes usar tu propio dominio

---

¿Empezamos? Te ayudo a crear los archivos necesarios paso a paso.