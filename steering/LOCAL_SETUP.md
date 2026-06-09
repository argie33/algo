# Local Development Setup Guide

This guide explains how to set up and verify that all backend and frontend issues are resolved.

## Prerequisites

- Node.js 18+ 
- PostgreSQL 14+ (local or accessible)
- PowerShell profile with environment variables configured (see below)

## Step 1: Configure Environment Variables

Add these to your PowerShell profile (`$PROFILE`):

```powershell
# Database (required)
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "postgres"
$env:DB_PASSWORD = "your_password"
$env:DB_NAME = "stocks"

# Alpaca API (optional - needed for portfolio sync)
$env:APCA_API_KEY_ID = "your_key"
$env:APCA_API_SECRET_KEY = "your_secret"
$env:ALPACA_PAPER_TRADING = "true"  # Use paper trading for testing

# Development mode
$env:NODE_ENV = "development"
```

Then reload PowerShell: `. $PROFILE`

## Step 2: Verify Database Connection

Test that PostgreSQL is accessible:

```powershell
# From PowerShell (requires psql installed)
psql -h localhost -U postgres -d stocks -c "SELECT 1;"
```

Expected output: `1` row with value `1`

## Step 3: Start Backend Service

```powershell
cd webapp/lambda
npm install  # First time only
npm start
```

**Expected output:**
```
✅ Database config loaded from environment: localhost:5432/stocks
[Startup] Loaded .env.local from ... (local development)
📱 Financial Dashboard API listening on port 3000
```

The backend will automatically:
- Initialize database connection
- Apply schema migration (fixes user_id type + adds missing columns)
- Create materialized views
- Initialize Alpaca sync scheduler (if credentials configured)

## Step 4: Verify Backend Health

From another PowerShell terminal:

```powershell
# Health check (no auth required)
curl http://localhost:3001/api/health

# Detailed health check
curl http://localhost:3001/api/health/detailed

# Database status
curl http://localhost:3001/api/database-status
```

**Expected responses:** 
- 200 status with `{"status": "healthy", "healthy": true}`
- Database should show "connected"

## Step 5: Start Frontend Development Server

```powershell
cd webapp/frontend
npm install  # First time only
npm run dev
```

**Expected output:**
```
VITE v4.x.x  ready in xxx ms

➜  Local:   http://localhost:5173/
➜  press h to show help
```

## Step 6: Test Frontend Connection

Open browser: `http://localhost:5173`

**Verify:**
- [ ] Home page loads without errors
- [ ] No console errors in browser DevTools
- [ ] API calls appear in DevTools Network tab
- [ ] Dashboard pages load (Markets, Signals, etc.)

## Step 7: Verify Database Schema Fix

Connect to database and check portfolio_holdings table:

```powershell
# Check user_id column type
psql -h localhost -U postgres -d stocks -c "
  SELECT column_name, data_type 
  FROM information_schema.columns 
  WHERE table_name = 'portfolio_holdings' 
  ORDER BY ordinal_position;"
```

**Expected:** `user_id` should be `character varying` (VARCHAR), NOT `integer`

**Check missing columns exist:**
```powershell
psql -h localhost -U postgres -d stocks -c "
  \d portfolio_holdings"
```

**Expected columns:**
- user_id (character varying)
- symbol (character varying)
- quantity (numeric)
- average_cost (numeric)
- current_price (numeric)
- market_value (numeric) ← Added by migration
- sector (character varying) ← Added by migration
- unrealized_pl (numeric) ← Added by migration
- unrealized_pl_percent (numeric) ← Added by migration
- created_at (timestamp) ← Added by migration
- updated_at (timestamp) ← Added by migration

## Verification Checklist

### Backend Issues Resolution

- [x] **Issue #1** - Database Type Mismatch
  - user_id is now VARCHAR(255) (verified in schema)
  - Alpaca sync will use Cognito UUIDs from req.user.sub

- [x] **Issue #2** - Sector Rotation Endpoint
  - Endpoint properly catches errors and returns sendDatabaseError
  - Will return 200 with empty items if table doesn't have data yet

- [x] **Issue #3** - Portfolio Holdings Insert
  - market_value column added to schema
  - All referenced columns exist

- [x] **Issue #4** - User ID Consistency
  - All routes use req.user.sub (Cognito UUID)
  - Auth middleware properly sets req.user
  - Database accepts VARCHAR user_id

- [ ] **Issue #8** - Environment Variables
  - [ ] DB_HOST configured
  - [ ] DB_PORT configured
  - [ ] DB_USER configured
  - [ ] DB_PASSWORD configured
  - [ ] DB_NAME configured
  - [ ] NODE_ENV set to "development"

- [x] **Issue #9** - Alpaca Credentials
  - Scheduler not disabled, just conditional on credentials
  - Can configure APCA_API_KEY_ID and APCA_API_SECRET_KEY to enable

### Frontend Issues Resolution

- [x] **Issue #5** - Frontend Dev Server Proxy
  - Vite configured with `/api` proxy to `http://localhost:3001`
  - Will work once backend is running on port 3001

- [x] **Issue #6** - React Error Boundaries
  - ErrorBoundary component implemented and used in App.jsx
  - Catches rendering errors gracefully

- [x] **Issue #7** - Config.js Cache
  - Handled by multi-layer cache invalidation (see steering/algo.md)
  - In development, uses relative paths with Vite proxy

## Troubleshooting

### Backend won't start

**Error:** `Error: ECONNREFUSED - cannot connect to database`

**Solution:** 
1. Verify PostgreSQL is running: `psql -U postgres`
2. Check DB_HOST, DB_PORT, DB_USER, DB_PASSWORD environment variables
3. Create database if missing: `psql -U postgres -c "CREATE DATABASE stocks;"`

### Frontend proxy errors (ECONNREFUSED)

**Error:** `http proxy error: ECONNREFUSED on /api/...`

**Solution:**
1. Ensure backend is running on port 3001
2. Check backend startup output for errors
3. Test health endpoint: `curl http://localhost:3001/api/health`

### API returns 5xx errors

**Solution:**
1. Check backend console for error messages
2. Verify database is accessible
3. Check that schema migration ran (see "Verify Database Schema Fix")

### Frontend shows blank/no data

**Solution:**
1. Check browser DevTools Network tab for failed API requests
2. Verify backend is returning data (not just errors)
3. Check ErrorBoundary console for React errors

## Next Steps

After successful verification:

1. Run integration tests: `npm test:integration`
2. Run security tests: `npm test:security`
3. Review committed schema fix: `git show 428fe12fa`
4. Test manual trades endpoint with Cognito UUID format

## Additional Resources

- Database schema migrations: `migrations/versions/`
- Backend routes: `webapp/lambda/routes/`
- Frontend API client: `webapp/frontend/src/services/api.js`
- Steering guide: `steering/algo.md`

