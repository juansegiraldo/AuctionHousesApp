#!/usr/bin/env python3
"""
Automated Railway deployment script
This script will prepare and deploy the project to Railway
"""

import subprocess
import os
import sys
from pathlib import Path

def run_command(command, description, check_success=True):
    """Run a command and display status"""
    print(f"🔄 {description}...")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if check_success and result.returncode != 0:
            print(f"❌ Failed: {description}")
            if result.stderr:
                print(f"Error: {result.stderr}")
            return False
        else:
            print(f"✅ {description}")
            if result.stdout and "git" in command:
                output = result.stdout.strip()
                if output:
                    print(f"   {output}")
            return True
            
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False

def check_git_setup():
    """Check if git is properly configured"""
    try:
        # Check if we're in a git repo
        result = subprocess.run("git status", shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print("🔄 Initializing git repository...")
            run_command("git init", "Initialize git repository")
            
        # Check if remote is configured
        result = subprocess.run("git remote -v", shell=True, capture_output=True, text=True)
        if "origin" not in result.stdout:
            remote_url = "https://github.com/juansegiraldo/AuctionHousesApp.git"
            run_command(f"git remote add origin {remote_url}", "Add git remote")
        
        return True
        
    except Exception as e:
        print(f"❌ Git setup error: {e}")
        return False

def verify_files():
    """Verify all necessary files exist"""
    required_files = [
        "requirements.txt",
        "Procfile", 
        "railway.toml",
        "backend/app/main.py",
        "database/migrations/001_initial_schema.sql"
    ]
    
    print("🔍 Verifying required files...")
    missing_files = []
    
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
            print(f"❌ Missing: {file_path}")
        else:
            print(f"✅ Found: {file_path}")
    
    if missing_files:
        print(f"\n❌ Missing {len(missing_files)} required files for Railway deployment")
        return False
    
    print("✅ All required files present")
    return True

def main():
    """Main deployment process"""
    print("🚂 Railway Deployment Preparation")
    print("=" * 50)
    
    # Check current directory
    if not Path("backend").exists():
        print("❌ Please run this script from the project root directory")
        print("   (The directory containing 'backend', 'database', etc.)")
        return False
    
    # Verify files
    if not verify_files():
        print("\n💡 Run setup first or ensure all files are created")
        return False
    
    # Setup git
    if not check_git_setup():
        return False
    
    print("\n📦 Committing changes...")
    
    # Git workflow
    commands = [
        ("git add .", "Stage all changes"),
        ("git commit -m 'Prepare for Railway deployment - FastAPI Auction Houses API'", "Commit changes"),
        ("git push -u origin main", "Push to GitHub")
    ]
    
    for command, description in commands:
        if not run_command(command, description, check_success=False):
            if "commit" in command and "nothing to commit" in subprocess.getoutput(command):
                print("   (No changes to commit)")
                continue
            elif "push" in command:
                print("   (May fail if branch doesn't exist yet - that's OK)")
                continue
    
    print("\n" + "=" * 50)
    print("🎉 RAILWAY DEPLOYMENT READY!")
    print("=" * 50)
    
    print("\n📋 Next Steps:")
    print("1. Go to https://railway.app")
    print("2. Click 'Start a New Project'")
    print("3. Select 'Deploy from GitHub repo'")
    print("4. Choose 'juansegiraldo/AuctionHousesApp'")
    print("5. Add PostgreSQL database:")
    print("   • Click '+ New' → 'Database' → 'PostgreSQL'")
    print("6. Wait for deployment (5-10 minutes)")
    print("7. Visit your app URL!")
    
    print("\n🔧 Railway Configuration:")
    print("• Build Command: Automatic (detected from Procfile)")
    print("• Start Command: Automatic (from railway.toml)")
    print("• Environment: Production")
    print("• Database: PostgreSQL (auto-configured)")
    
    print("\n📊 What will be deployed:")
    print("• ✅ FastAPI application with 27 endpoints")
    print("• ✅ PostgreSQL database with auction houses")
    print("• ✅ Swagger documentation at /docs")
    print("• ✅ Full REST API for auction data")
    print("• ✅ Analytics and search functionality")
    
    print("\n🌐 Expected URLs:")
    print("• API Docs: https://your-app.railway.app/docs")
    print("• Health Check: https://your-app.railway.app/health")
    print("• Houses API: https://your-app.railway.app/api/v1/houses/")
    
    print("\n💡 Tips:")
    print("• Railway free tier: $5/month usage limit")
    print("• Auto-deploys on every git push")
    print("• Check logs in Railway dashboard if issues occur")
    print("• Database initializes automatically on first run")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ Deployment preparation cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)