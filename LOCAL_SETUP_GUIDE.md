# Local Development Setup Guide

Complete step-by-step guide to get the site fully operational on your local machine.

## Prerequisites Check

Before starting, ensure you have:
- ✅ Python 3.11+ (`python --version`)
- ✅ Node.js 20.19+ (`node --version`)
- ✅ npm 9.0+ (`npm --version`)
- ✅ PostgreSQL 14+ (running)

## Step 1: Set Up PostgreSQL Database

### Option A: Docker (Recommended - Fastest)

If you have Docker installed:

```powershell
# Run PostgreSQL in Docker
docker run --name algo-postgres `
  -e POSTGRES_DB=stocks `
  -e POSTGRES_USER=stocks `
  -e POSTGRES_PASSWORD=stocks `
  -p 5432:5432 `
  -d postgres:14-alpine

# Verify it's running
docker ps | Select-String postgres
```

### Option B: Local PostgreSQL Installation

If PostgreSQL is already installed locally:

1. **Start PostgreSQL service**
   ```powershell
   # Windows (if using installer)
   net start PostgreSQL14  # or your version
   
   # Verify with psql
   psql --version
   ```

2. **Create database and user** (only if not already done)
   ```powershell
   psql -U postgres -c "CREATE DATABASE stocks;"
   psql -U postgres -c "CREATE USER stocks WITH PASSWORD 'stocks';"
   psql -U postgres -c "ALTER USER stocks CREATEDB;"
   psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;"
   ```

3. **Test connection**
   ```powershell
   psql -h localhost -U stocks -d stocks -c "SELECT 1;"
   # Should output: ?column?
   #     1
   ```

## Step 2: Initialize Database Schema

Once PostgreSQL is running, create all required tables:

```powershell
# Set database environment variables
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_PASSWORD = "stocks"
$env:DB_NAME = "stocks"

# Apply schema
python scripts/apply-database-schema.py
```

**Expected output:**
```
====================================================================
DATABASE SCHEMA INITIALIZATION
====================================================================

Connecting to database...
[OK] Connected

Loading schema from: C:\...\lambda\db-init\schema.sql
[OK] Schema loaded (XXX bytes)

Applying schema...
Executing schema SQL (this may take a minute)...
[OK] Schema applied successfully!
```

## Step 3: Start the API Dev Server

In **Terminal 1** (Backend), run:

```powershell
# Set LOCAL_MODE to use localhost postgres instead of AWS Secrets Manager
$env:LOCAL_MODE = "true"
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_PASSWORD = "stocks"
$env:DB_NAME = "stocks"

# Start the dev server
cd lambda/api
python dev_server.py
```

**Expected output:**
```
[DEV_SERVER] LOCAL_MODE=true, using localhost postgres
[DEV_SERVER] Starting development server on http://0.0.0.0:3001
...
```

The server will keep running. Leave this terminal open.

## Step 4: Install Frontend Dependencies

In **Terminal 2** (Frontend setup), run:

```powershell
cd webapp/frontend
npm install
```

This installs all React dependencies (takes ~2 minutes).

## Step 5: Start the Frontend Dev Server

In **Terminal 2** (Frontend), run:

```powershell
npm run dev
```

**Expected output:**
```
  VITE v7.1.3  ready in 234 ms

  ➜  Local:   http://localhost:5173/
  ➜  press h + enter to show help
```

## Step 6: Verify Everything is Working

### 1. Open the website
- Navigate to **http://localhost:5173** in your browser

### 2. Check for errors in browser console
- Press **F12** → **Console** tab
- Should show no errors about API connectivity

### 3. Test an API call
- Click any dashboard feature (e.g., Portfolio, Market, etc.)
- Check the dev server terminal (Terminal 1) - should show request logs
- No 5xx errors should appear

### 4. Verify database connectivity
- Go to **Settings → System Health** (if available)
- Should show "✓ Database Connected"

## Troubleshooting

### Port 3001 Already In Use

```powershell
# Kill the process using port 3001
$proc = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue
if ($proc) {
    Stop-Process -Id $proc.OwningProcess -Force
}

# Then restart dev_server.py
```

### Database Connection Failed

**Error:** "FATAL: role 'stocks' does not exist"

```powershell
# Check if user exists
psql -U postgres -c "\du" | Select-String stocks

# If not, create it
psql -U postgres -c "CREATE USER stocks WITH PASSWORD 'stocks';"
psql -U postgres -c "ALTER USER stocks CREATEDB;"
```

**Error:** "FATAL: database 'stocks' does not exist"

```powershell
# Create the database
psql -U postgres -c "CREATE DATABASE stocks OWNER stocks;"

# Then re-apply schema
python scripts/apply-database-schema.py
```

### npm install Issues

```powershell
# Clear npm cache and try again
npm cache clean --force
cd webapp/frontend
npm install --legacy-peer-deps
```

### Frontend Can't Reach API

Check in browser **F12 → Network**:
- API calls should go to `http://localhost:3001`
- Responses should be 200 or proper error codes, not 404

If requests are 404:
1. Restart dev_server.py
2. Check that `LOCAL_MODE=true` is set
3. Verify database connection works (`psql -h localhost -U stocks -d stocks -c "SELECT 1;"`)

## Development Workflow

### Making Code Changes

**Backend changes** (files in `lambda/api/`, `utils/`, etc.):
1. Edit the file
2. Dev server auto-restarts (or manually restart Terminal 1)
3. Refresh browser

**Frontend changes** (files in `webapp/frontend/src/`):
1. Edit the file
2. Vite auto-reloads (usually within seconds)
3. Check browser - hot reload should apply changes

### Running Tests

```powershell
# Unit tests
pytest tests/unit -v

# Frontend tests
cd webapp/frontend
npm test

# Integration tests (requires running dev_server)
pytest tests/integration -v
```

## Next Steps

### Local Development Complete ✓
- Site is fully functional on http://localhost:5173
- All data comes from local PostgreSQL database
- Changes auto-reload in browser

### Production Deployment (June 15)
When ready to deploy to AWS:
1. See `terraform/DEPLOYMENT_GUIDE.md`
2. Push to GitHub main branch
3. GitHub Actions automatically deploys infrastructure
4. Terraform outputs are stored in AWS Secrets Manager
5. Dashboard fetches config automatically

### Populating Data

To add test data to your local database:

```powershell
# Load price data (requires yfinance API access)
cd loaders
python load_prices.py --symbols "AAPL,MSFT,TSLA"

# Or run all loaders
python load_prices.py

# Monitor progress
python scripts/check_price_coverage.py
```

## Quick Reference

| Component | URL | Port | Terminal |
|-----------|-----|------|----------|
| Frontend | http://localhost:5173 | 5173 | Terminal 2 |
| API Backend | http://localhost:3001 | 3001 | Terminal 1 |
| PostgreSQL | localhost:5432 | 5432 | (running) |

## Environment Variables (for reference)

**Database (Local Development):**
```powershell
$env:LOCAL_MODE = "true"
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_PASSWORD = "stocks"
$env:DB_NAME = "stocks"
```

**API Dev Mode:**
```powershell
$env:DEV_BYPASS_AUTH = "true"   # Skip Cognito, use dev tokens
$env:ENVIRONMENT = "development" # Enable dev logging
```
