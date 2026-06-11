# Dashboard Data Wiring Diagnosis

## Problem
Dashboard shows "no data" and "API unavailable" errors for most sections because the database tables that the API endpoints query don't exist or are empty.

##  Current Wiring Status

### Frontend → API (✓ CORRECT)
The PortfolioDashboard.jsx correctly calls these API endpoints:
- `/api/algo/status` → fetches algo_status
- `/api/algo/positions` → fetches algo_positions  
- `/api/algo/performance` → fetches algo_performance
- `/api/algo/trades?limit=200` → fetches algo_trades_recent
- `/api/algo/markets` → fetches algo_markets
- `/api/algo/equity-curve?limit=180` → fetches algo_equity_curve
- `/api/algo/circuit-breakers` → fetches algo_circuit_breakers

**Status:** Frontend is properly configured, endpoints are in correct locations.

### API → Database (✗ BROKEN)
The Lambda API routes (webapp/lambda/routes/algo.js) are implemented and query these tables:
- `algo_portfolio_snapshots` - ✓ EXISTS (8 rows, but no date) 
- `algo_performance_daily` - ✗ MISSING
- `circuit_breaker_status` - ✗ MISSING
- `algo_positions_with_risk` - ✗ MISSING (should be a view)
- `algo_trades` - ✗ MISSING
- `market_health_daily` - ✗ MISSING
- `buy_sell_daily` - ✗ MISSING
- `signal_quality_scores` - ✗ MISSING

**Status:** API routes exist but database tables are missing/empty.

### Database ← Loaders (✗ NOT RUNNING)
Data loaders that should populate these tables:
- `loaders/load_algo_performance_daily.py` → `algo_performance_daily`
- `loaders/compute_circuit_breakers.py` → `circuit_breaker_status`
- `loaders/load_prices.py` → market data
- `loaders/load_buy_sell_daily.py` → `buy_sell_daily`
- `loaders/load_market_health_daily.py` → `market_health_daily`
- etc. (27 total loaders per steering/algo.md)

**Status:** Loaders haven't been run, so tables are empty.

## Root Causes

### 1. Missing Database Schema
The database schema is incomplete because:
- `lambda/db-init/schema.sql` has dependency issues when applied directly
- Local database doesn't have full migration history
- Production uses GitHub Actions to apply schema correctly

**Fix:** Need to initialize schema properly before running loaders.

### 2. Missing Database Initialization
Database initialization in production is handled by:
- GitHub Actions workflow (`deploy-all-infrastructure.yml`)
- db-init Lambda function that reads `lambda/db-init/schema.sql`
- Removes Lambda after execution (ephemeral resource)

**Local workaround:** Manually apply schema or use PostgreSQL command-line tools.

### 3. Loaders Haven't Run
Daily loader schedule (from steering/algo.md):
- 2:00 AM ET: morning-prep-pipeline (stock prices, technicals)
- 4:05 PM ET: EOD pipeline (9 core loaders)
- 4:30 PM ET: compute_circuit_breakers
- 4:45 PM ET: compute_performance_metrics

**Status:** Loaders run on EventBridge schedules in production, but local database hasn't been populated.

## Solution Path

### For Local Development (Current Situation)

1. **Initialize Database Schema**
   ```bash
   # Option A: Use psql directly (if PostgreSQL tools installed)
   psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f lambda/db-init/schema.sql
   
   # Option B: Fix Python script (in progress)
   python scripts/apply-database-schema.py
   ```

2. **Run Core Loaders** (in this order)
   ```bash
   python loaders/load_stock_symbols.py              # 2-5 min
   python loaders/load_prices.py                     # 10-30 min
   python loaders/load_market_health_daily.py        # 1-2 min
   python loaders/load_technical_data_daily.py       # 30-60 min
   python loaders/load_buy_sell_daily.py             # 5-10 min
   python loaders/load_signal_quality_scores.py      # 5-10 min
   python loaders/load_swing_trader_scores.py        # 5-10 min
   python loaders/load_algo_metrics_daily.py         # 2-5 min
   ```

3. **Verify Data Was Loaded**
   ```bash
   python scripts/diagnose-dashboard-data.py
   ```

4. **Check Dashboard**
   ```bash
   # Start local dev server
   cd webapp/frontend && npm run dev
   # Navigate to Portfolio dashboard
   ```

### For Production (AWS)
No action needed - GitHub Actions workflow handles:
1. GitHub Actions (deploy-all-infrastructure.yml) creates db-init Lambda
2. Lambda applies schema.sql to RDS
3. EventBridge triggers loaders on schedule
4. Loaders populate database
5. API queries populated tables
6. Frontend displays data

## Data Flow Diagram

```
PRODUCTION FLOW:
===============
EventBridge (2 AM) → Lambda (algo-step-functions) → ECS Tasks (loaders)
                                                        ↓
                                                    RDS Database
                                                        ↓
Lambda API Gateway Request → Lambda (algo-api) → Database Query → JSON Response
                                                        ↑
                                                   algo.js routes
                                                        ↓
                                          CloudFront (PortfolioDashboard.jsx)
                                                        ↓
                                                   Browser (user sees data)

LOCAL DEV FLOW:
================
Python script (loaders) → Local/RDS Database
                              ↓
npm run dev (API proxy) → localhost:3000/api → Lambda/local API → Database Query
                                                                      ↑
                                                                  algo.js routes
                                                                      ↓
                                          React (PortfolioDashboard.jsx)
                                                      ↓
                                            Browser (user sees data)
```

## Environment Configuration

### ⚠️ CRITICAL: Current Setup is Using LOCAL Database (NOT AWS!)

**Current Configuration:**
- DB_HOST: **localhost** (local PostgreSQL)
- DB_NAME: **stocks** (local database)
- DB_USER: stocks
- Database Status: **LOCAL DEVELOPMENT MODE** (not getting AWS data)

**To use AWS RDS (recommended for real data):**
```powershell
.\scripts\setup-database-config.ps1 -UseAWS
```

This script will:
1. Refresh AWS credentials from Secrets Manager
2. Fetch RDS endpoint from AWS Secrets Manager
3. Update your PowerShell profile with AWS database config
4. Verify connection to AWS RDS

**To switch back to local for development:**
```powershell
.\scripts\setup-database-config.ps1 -UseLocal
```

**To check current configuration:**
```powershell
.\scripts\setup-database-config.ps1 -Show
```

### Production Configuration (AWS RDS)
- DB_HOST: algo-db.cvjv6oql86ak.us-east-1.rds.amazonaws.com
- DB_NAME: algo_trades
- DB_USER: From AWS Secrets Manager (algo/database)
- DB_PASSWORD: From AWS Secrets Manager (algo/database)

### Local Development Configuration
- DB_HOST: localhost
- DB_NAME: stocks (or your local DB name)
- DB_USER: Local PostgreSQL username
- DB_PASSWORD: Local PostgreSQL password

**Why use local for development?**
- Faster iteration without network latency
- Can test with dummy data
- No AWS costs
- Offline testing capability

**Why use AWS RDS ultimately?**
- Real production data
- Loaders populate continuously
- Dashboard shows actual trading state
- Data shared across team

## Next Steps

1. **Immediate:** Try to apply schema using PostgreSQL tools
   ```bash
   psql -h $env:DB_HOST -U $env:DB_USER -d $env:DB_NAME -f lambda/db-init/schema.sql
   ```

2. **If schema succeeds:** Run a single loader to test
   ```bash
   python loaders/load_stock_symbols.py
   ```

3. **If loader succeeds:** Run more loaders in sequence

4. **If data loads:** Verify dashboard shows data
   ```bash
   python scripts/diagnose-dashboard-data.py
   ```

## Testing Checklist

- [ ] Database schema applied successfully
- [ ] algo_portfolio_snapshots table has data
- [ ] algo_performance_daily table has data
- [ ] circuit_breaker_status table has data
- [ ] `/api/algo/performance` returns data (not empty)
- [ ] `/api/algo/circuit-breakers` returns data
- [ ] Dashboard shows metrics (not "no data")
- [ ] Dashboard shows performance ratios (Sharpe, Sortino, Calmar)
- [ ] Dashboard shows circuit breaker status

## Key Files to Review

- **API Routes:** `webapp/lambda/routes/algo.js` (endpoints query these tables)
- **Frontend Calls:** `webapp/frontend/src/pages/PortfolioDashboard.jsx` (calls these endpoints)
- **Database Schema:** `lambda/db-init/schema.sql` (defines all tables)
- **Loaders:** `loaders/load_*.py` and `loaders/compute_*.py` (populate tables)
- **Configuration:** `steering/algo.md` (describes data flow and schedule)
