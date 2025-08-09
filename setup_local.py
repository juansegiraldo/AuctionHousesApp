#!/usr/bin/env python3
"""
Local development setup without Docker
This script sets up the project for local development using local services
"""

import subprocess
import sys
import os
import urllib.request
import zipfile
import shutil
from pathlib import Path
import json

def run_command(command, description, check_success=True, cwd=None):
    """Run a command and display status"""
    print(f"🔄 {description}...")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd)
        
        if check_success and result.returncode != 0:
            print(f"❌ Failed: {description}")
            if result.stderr:
                print(f"Error: {result.stderr}")
            return False
        else:
            print(f"✅ {description}")
            if result.stdout and not check_success:
                print(f"Output: {result.stdout.strip()}")
            return True
            
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False

def check_python():
    """Check Python version"""
    try:
        version = subprocess.check_output([sys.executable, "--version"], text=True)
        print(f"✅ Python: {version.strip()}")
        if "3.11" not in version and "3.10" not in version and "3.9" not in version:
            print("⚠️  Python 3.9+ recommended")
        return True
    except:
        print("❌ Python not found")
        return False

def setup_virtual_environment():
    """Create and setup virtual environment"""
    venv_path = Path("venv")
    
    if venv_path.exists():
        print("✅ Virtual environment already exists")
        return True
    
    success = run_command(
        f"{sys.executable} -m venv venv",
        "Create virtual environment"
    )
    
    if not success:
        return False
    
    # Activate and install requirements
    if os.name == 'nt':  # Windows
        activate_cmd = r"venv\Scripts\activate && python -m pip install --upgrade pip && pip install -r backend\requirements.txt"
    else:  # Unix/Linux
        activate_cmd = "source venv/bin/activate && python -m pip install --upgrade pip && pip install -r backend/requirements.txt"
    
    success = run_command(
        activate_cmd,
        "Install Python dependencies"
    )
    
    return success

def setup_postgresql_portable():
    """Download and setup portable PostgreSQL (Windows)"""
    if os.name != 'nt':
        print("❌ Portable PostgreSQL only available on Windows")
        print("Please install PostgreSQL manually: https://www.postgresql.org/download/")
        return False
    
    pg_dir = Path("tools/postgresql")
    if pg_dir.exists():
        print("✅ PostgreSQL already downloaded")
        return True
    
    print("🔄 Downloading portable PostgreSQL...")
    
    # Create tools directory
    Path("tools").mkdir(exist_ok=True)
    
    # Download PostgreSQL portable
    pg_url = "https://get.enterprisedb.com/postgresql/postgresql-15.4-1-windows-x64-binaries.zip"
    pg_zip = "tools/postgresql.zip"
    
    try:
        urllib.request.urlretrieve(pg_url, pg_zip)
        print("✅ PostgreSQL downloaded")
        
        # Extract
        with zipfile.ZipFile(pg_zip, 'r') as zip_ref:
            zip_ref.extractall("tools")
        
        # Rename extracted folder
        extracted_dir = Path("tools/pgsql")
        if extracted_dir.exists():
            extracted_dir.rename("tools/postgresql")
        
        # Cleanup
        os.remove(pg_zip)
        
        print("✅ PostgreSQL extracted")
        return True
        
    except Exception as e:
        print(f"❌ Error downloading PostgreSQL: {e}")
        print("Please install PostgreSQL manually")
        return False

def setup_redis_portable():
    """Download and setup Redis for Windows"""
    if os.name != 'nt':
        print("❌ Please install Redis manually:")
        print("Ubuntu/Debian: sudo apt install redis-server")
        print("MacOS: brew install redis")
        return False
    
    redis_dir = Path("tools/redis")
    if redis_dir.exists():
        print("✅ Redis already downloaded")
        return True
    
    print("🔄 Downloading Redis for Windows...")
    
    # Download Redis
    redis_url = "https://github.com/microsoftarchive/redis/releases/download/win-3.0.504/Redis-x64-3.0.504.zip"
    redis_zip = "tools/redis.zip"
    
    try:
        urllib.request.urlretrieve(redis_url, redis_zip)
        print("✅ Redis downloaded")
        
        # Extract
        with zipfile.ZipFile(redis_zip, 'r') as zip_ref:
            zip_ref.extractall("tools/redis")
        
        # Cleanup
        os.remove(redis_zip)
        
        print("✅ Redis extracted")
        return True
        
    except Exception as e:
        print(f"❌ Error downloading Redis: {e}")
        print("You can skip Redis for basic API testing")
        return False

def create_local_env():
    """Create .env file for local development"""
    env_content = """# Local development environment
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/auction_houses
REDIS_URL=redis://localhost:6379
ENVIRONMENT=development
SECRET_KEY=local-dev-secret-key-change-in-production
SCRAPING_ENABLED=true
ALLOWED_HOSTS=*
"""
    
    env_path = Path(".env.local")
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print("✅ Created .env.local file")
    return True

def create_database_setup():
    """Create database setup script"""
    db_script = """
-- Create database and user for local development
CREATE DATABASE auction_houses;
CREATE USER auction_user WITH PASSWORD 'auction_pass';
GRANT ALL PRIVILEGES ON DATABASE auction_houses TO auction_user;

-- Connect to the database and run migrations
\\c auction_houses;

-- You can now run the SQL files from database/migrations/ manually
"""
    
    Path("tools").mkdir(exist_ok=True)
    with open("tools/setup_database.sql", 'w') as f:
        f.write(db_script)
    
    print("✅ Created database setup script")

def create_start_script():
    """Create local development start script"""
    
    if os.name == 'nt':  # Windows
        start_script = """@echo off
echo Starting Auction Houses API (Local Development)
echo ================================================

REM Start PostgreSQL (if using portable)
if exist tools\\postgresql\\bin\\pg_ctl.exe (
    echo Starting PostgreSQL...
    tools\\postgresql\\bin\\pg_ctl.exe -D data\\postgres -l logs\\postgres.log start
)

REM Start Redis (if using portable)
if exist tools\\redis\\redis-server.exe (
    echo Starting Redis...
    start /B tools\\redis\\redis-server.exe
)

REM Wait a moment for services to start
timeout /t 3 /nobreak >nul

REM Activate virtual environment and start API
echo Starting FastAPI application...
call venv\\Scripts\\activate.bat
set DATABASE_URL=postgresql://postgres:postgres@localhost:5432/auction_houses
set REDIS_URL=redis://localhost:6379
set ENVIRONMENT=development

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend

pause
"""
        with open("start_local.bat", 'w') as f:
            f.write(start_script)
        print("✅ Created start_local.bat")
        
    else:  # Unix/Linux
        start_script = """#!/bin/bash
echo "Starting Auction Houses API (Local Development)"
echo "================================================"

# Start services if available
if command -v redis-server >/dev/null 2>&1; then
    echo "Starting Redis..."
    redis-server --daemonize yes
fi

if command -v pg_ctl >/dev/null 2>&1; then
    echo "Starting PostgreSQL..."
    pg_ctl -D data/postgres -l logs/postgres.log start
fi

# Wait for services
sleep 3

# Activate virtual environment and start API
echo "Starting FastAPI application..."
source venv/bin/activate
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/auction_houses"
export REDIS_URL="redis://localhost:6379"
export ENVIRONMENT="development"

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend
"""
        with open("start_local.sh", 'w') as f:
            f.write(start_script)
        os.chmod("start_local.sh", 0o755)
        print("✅ Created start_local.sh")

def create_instructions():
    """Create detailed setup instructions"""
    instructions = """# Local Development Setup (Without Docker)

## 🚀 Quick Start

### Windows Users:
1. Run: `python setup_local.py`
2. Install PostgreSQL manually if portable download fails
3. Run database migrations manually
4. Execute: `start_local.bat`

### Linux/Mac Users:
1. Install PostgreSQL: `sudo apt install postgresql postgresql-contrib` (Ubuntu)
2. Install Redis: `sudo apt install redis-server` (Ubuntu)
3. Run: `python setup_local.py`
4. Execute: `./start_local.sh`

## 📋 Manual Setup Steps

### 1. Database Setup
```bash
# Start PostgreSQL service
sudo systemctl start postgresql  # Linux
brew services start postgresql   # Mac

# Create database
sudo -u postgres psql
CREATE DATABASE auction_houses;
CREATE USER auction_user WITH PASSWORD 'auction_pass';
GRANT ALL PRIVILEGES ON DATABASE auction_houses TO auction_user;
\\q

# Run migrations
psql -U postgres -d auction_houses -f database/migrations/001_initial_schema.sql
psql -U postgres -d auction_houses -f database/seeds/002_auction_houses_data.sql
```

### 2. Python Setup
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\\Scripts\\activate   # Windows

pip install -r backend/requirements.txt
```

### 3. Start API
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 🌐 Access Points
- API Documentation: http://localhost:8000/docs
- API Base: http://localhost:8000/api/v1
- Health Check: http://localhost:8000/health

## 🧪 Testing
```bash
python scripts/test_api.py
python scripts/populate_test_data.py
```

## ⚡ Alternative: SQLite (Simplest)
If PostgreSQL is too complex, you can modify the DATABASE_URL to use SQLite:
```
DATABASE_URL=sqlite:///./auction_houses.db
```
"""
    
    with open("LOCAL_SETUP.md", 'w') as f:
        f.write(instructions)
    
    print("✅ Created LOCAL_SETUP.md with detailed instructions")

def main():
    """Main setup process"""
    print("🏠 Local Development Setup (No Docker)")
    print("=" * 50)
    
    # Check prerequisites
    if not check_python():
        print("❌ Please install Python 3.9+ first")
        return False
    
    # Create directories
    Path("tools").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    
    # Setup Python environment
    if not setup_virtual_environment():
        print("❌ Failed to setup Python environment")
        return False
    
    # Setup services (optional)
    print("\n🗄️ Setting up database services...")
    setup_postgresql_portable()  # May fail, that's OK
    setup_redis_portable()       # May fail, that's OK
    
    # Create configuration files
    print("\n⚙️ Creating configuration files...")
    create_local_env()
    create_database_setup()
    create_start_script()
    create_instructions()
    
    # Final instructions
    print("\n" + "=" * 50)
    print("🎉 LOCAL SETUP COMPLETE!")
    print("=" * 50)
    
    print("\n📋 Next Steps:")
    print("1. Install PostgreSQL manually if needed:")
    print("   • Windows: https://www.postgresql.org/download/windows/")
    print("   • Mac: brew install postgresql")
    print("   • Ubuntu: sudo apt install postgresql postgresql-contrib")
    
    print("\n2. Setup database:")
    print("   • Create database: 'auction_houses'")
    print("   • Run SQL files from database/migrations/")
    
    print("\n3. Start the application:")
    if os.name == 'nt':
        print("   • Double-click: start_local.bat")
        print("   • Or run: python -m uvicorn app.main:app --reload --app-dir backend")
    else:
        print("   • Run: ./start_local.sh")
        print("   • Or run: python -m uvicorn app.main:app --reload --app-dir backend")
    
    print("\n📚 Documentation:")
    print("   • See LOCAL_SETUP.md for detailed instructions")
    print("   • API will be at: http://localhost:8000/docs")
    
    return True

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Setup interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)