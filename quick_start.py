#!/usr/bin/env python3
"""
Quick start script for Auction Houses Database Application
This script will guide you through the setup process
"""

import subprocess
import time
import sys
import requests
from pathlib import Path

def run_command(command, description, check_success=True):
    """Run a command and display status"""
    print(f"🔄 {description}...")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if check_success and result.returncode != 0:
            print(f"❌ Failed: {description}")
            print(f"Error: {result.stderr}")
            return False
        else:
            print(f"✅ {description}")
            return True
            
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False

def check_docker():
    """Check if Docker is running"""
    try:
        result = subprocess.run("docker --version", shell=True, capture_output=True)
        if result.returncode == 0:
            print("✅ Docker is available")
            return True
        else:
            print("❌ Docker is not available")
            return False
    except:
        print("❌ Docker is not installed")
        return False

def wait_for_api(url="http://localhost:8000", max_attempts=30):
    """Wait for API to become available"""
    print("🔄 Waiting for API to start...")
    
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                print("✅ API is ready!")
                return True
        except:
            pass
        
        time.sleep(2)
        if attempt % 5 == 0:
            print(f"   Still waiting... ({attempt}/{max_attempts})")
    
    print("❌ API failed to start within timeout")
    return False

def main():
    """Main setup process"""
    print("🚀 Auction Houses Database - Quick Start")
    print("=" * 50)
    
    # Check prerequisites
    if not check_docker():
        print("\n❌ Please install Docker first: https://docker.com/get-started")
        return False
    
    # Check if we're in the right directory
    if not Path("docker-compose.yml").exists():
        print("❌ Please run this script from the project root directory")
        return False
    
    # Create .env file if it doesn't exist
    if not Path(".env").exists():
        print("🔄 Creating .env file...")
        run_command("cp .env.example .env", "Copy environment file", False)
    else:
        print("✅ .env file already exists")
    
    # Start services
    print("\n🐳 Starting Docker services...")
    success = run_command(
        "docker-compose up -d postgres redis backend celery_worker celery_beat",
        "Start backend services"
    )
    
    if not success:
        print("❌ Failed to start services")
        return False
    
    # Wait for API to be ready
    if not wait_for_api():
        print("❌ API not accessible")
        print("Try running: docker-compose logs backend")
        return False
    
    # Populate test data
    print("\n📊 Creating test data...")
    success = run_command(
        "python scripts/populate_test_data.py",
        "Populate database with sample data"
    )
    
    if not success:
        print("⚠️  Test data creation failed, but API should still work")
    
    # Test API
    print("\n🧪 Testing API endpoints...")
    success = run_command(
        "python scripts/test_api.py",
        "Run API tests",
        False  # Don't fail if some tests fail
    )
    
    # Display results
    print("\n" + "=" * 50)
    print("🎉 SETUP COMPLETE!")
    print("=" * 50)
    
    print("\n📍 Access Points:")
    print("   • API Documentation: http://localhost:8000/docs")
    print("   • API Base URL: http://localhost:8000/api/v1")
    print("   • Health Check: http://localhost:8000/health")
    
    print("\n📋 Quick Commands:")
    print("   • make logs-api          # View API logs")
    print("   • make test-api         # Test all endpoints")
    print("   • make db-shell        # Access database")
    print("   • make status          # Check service status")
    print("   • make down            # Stop all services")
    
    print("\n🔗 Example API Calls:")
    print("   • GET  /houses/               # List auction houses")
    print("   • GET  /auctions/?limit=10    # List recent auctions")
    print("   • GET  /lots/search/?q=art    # Search for art lots")
    print("   • GET  /analytics/summary/    # Market summary")
    
    print("\n📚 Documentation:")
    print("   • README.md - Full project documentation")
    print("   • CLAUDE.md - Development guidance")
    print("   • AUCTION_HOUSES_APP_PLAN.md - Complete project plan")
    
    print("\n✨ The auction houses database is ready for use!")
    
    return True

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Setup interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)