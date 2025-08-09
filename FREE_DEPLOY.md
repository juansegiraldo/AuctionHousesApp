# 🆓 Free Deployment Guide

Your Auction Houses API can be deployed completely FREE using these services:

## Option 1: Render.com (Recommended)

### What's Free:
- ✅ Web service: 750 hours/month (enough for 1 app)
- ✅ PostgreSQL: FREE for 90 days, then $7/month
- ✅ Auto-deploys from GitHub
- ✅ HTTPS included
- ✅ Custom domains

### Steps:
1. Go to **https://render.com**
2. Sign up with GitHub
3. Click **"New +"** → **"Web Service"**
4. Connect your GitHub repo: `juansegiraldo/AuctionHousesApp`
5. Configure:
   - **Name**: `auction-houses-api`
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend`
6. Add PostgreSQL database:
   - Click **"New +"** → **"PostgreSQL"**
   - Name: `auction-houses-db`
7. Connect database in web service environment variables:
   - Key: `DATABASE_URL`
   - Value: Select your PostgreSQL database

## Option 2: Supabase + Render (100% Free Forever)

### Database: Supabase (Free PostgreSQL)
1. Go to **https://supabase.com**
2. Create free project
3. Get connection string from Settings → Database

### App: Render Web Service
1. Use Render free web service (same as above)
2. Set `DATABASE_URL` to your Supabase connection string

## Option 3: Vercel + Supabase (Serverless)

### Convert to Serverless:
- Use Vercel for hosting
- Convert FastAPI to serverless functions
- Use Supabase for database

## 🚀 Recommended: Render.com

**Why Render is best for your FastAPI app:**
- ✅ Native Python support
- ✅ Persistent storage
- ✅ Always-on service
- ✅ Easy PostgreSQL integration
- ✅ 750 free hours = 31 days continuous running

## After Deployment

Your app will be available at:
- **API Docs**: `https://your-app-name.onrender.com/docs`
- **Health Check**: `https://your-app-name.onrender.com/health`
- **API Base**: `https://your-app-name.onrender.com/api/v1/`

## Free Tier Limits

**Render Free Plan:**
- 750 compute hours/month
- 512 MB RAM
- Sleeps after 15 minutes of inactivity
- Wakes up on first request (cold start ~30 seconds)

**Perfect for:**
- Portfolio projects
- Demos
- Learning
- Low-traffic applications