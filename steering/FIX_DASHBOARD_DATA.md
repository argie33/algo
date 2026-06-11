# Dashboard Data Missing - Root Cause & Solution

## Problem Summary
Dashboard shows multiple "no data" and "API unavailable" errors because:
1. **Using LOCAL database (localhost)** instead of AWS RDS
2. **Database schema incomplete** (local DB doesn't have all required tables)
3. **Loaders haven't been run** (no data populated into existing tables)

## Root Cause Analysis

### 1. Wrong Database (LOCAL vs AWS)
```
Current: DB_HOST = localhost
Status:  USING LOCAL DATABASE (not AWS RDS)
```

Your dashboard is trying to query a local PostgreSQL database that:
- Doesn't have the full schema
- Doesn't have any data populated
- Isn't updated by the loaders

**The loaders run on AWS**, so data only gets populated in **AWS RDS**, not your local database!

### 2. Incomplete Schema
Tried to apply schema.sql to local database and encountered issues:
- schema.sql has complex PostgreSQL DDL that requires careful ordering
- Some tables reference columns that don't exist yet
- Migration dependencies not properly resolved
- Production uses GitHub Actions workflow to handle this correctly

### 3. Missing Data
Even if schema existed, without loaders running:
- `algo_performance_daily` table would be empty
- `circuit_breaker_status` table would be empty
- `algo_trades` table would be empty
- Dashboard would show "no data"

## The Solution (Pick One)

### OPTION A: Use AWS RDS (RECOMMENDED) 
This gets you real data that loaders populate continuously.

**1. Switch to AWS database:**
```powershell
.\scripts\setup-database-config.ps1 -UseAWS
```

This script:
- Runs refresh-aws-credentials.ps1 to get current AWS creds
- Fetches RDS endpoint from AWS Secrets Manager
- Updates your PowerShell profile with AWS database config
- Verifies connection to AWS RDS

**2. Check current configuration:**
```powershell
.\scripts\setup-database-config.ps1 -Show
```

You should see:
```
Target:       AWS-RDS
DB_HOST:      algo-db.cvjv6oql86ak.us-east-1.rds.amazonaws.com
DB_NAME:      algo_trades
DB_USER:      postgres
```

**3. Verify dashboard now shows data:**
```
# The API will query AWS RDS
# If loaders have run, you'll see:
✓ Portfolio Value
✓ Performance metrics  
✓ Risk metrics
✓ Circuit breaker status
✓ Trade history
```

### OPTION B: Use Local Database (For Development Only)
This is useful if you want to develop offline or test with dummy data.

**1. Switch to local database:**
```powershell
.\scripts\setup-database-config.ps1 -UseLocal
```

**2. Initialize database schema:**
```bash
# Option A: Use PostgreSQL command-line (if installed)
psql -h localhost -U stocks -d stocks -f lambda/db-init/schema.sql

# Option B: Use Python script (handles complex SQL)
python scripts/apply-database-schema.py
```

**3. Populate with data (run loaders in this order):**
```bash
python loaders/load_stock_symbols.py
python loaders/load_prices.py
python loaders/load_market_health_daily.py
python loaders/load_technical_data_daily.py
python loaders/load_buy_sell_daily.py
python loaders/load_signal_quality_scores.py
python loaders/load_swing_trader_scores.py
```

(Each loader takes 2-60 minutes depending on data size)

**4. Verify data loaded:**
```bash
python scripts/diagnose-dashboard-data.py
```

You should see:
```
✓ algo_portfolio_snapshots         OK (8 rows)
✓ algo_performance_daily           OK (1 row)
✓ circuit_breaker_status           OK (1 row)
```

## Why This Matters

### Frontend → API → Database
```
PortfolioDashboard.jsx  (React component)
         ↓
    calls /api/algo/performance
         ↓
    Lambda API (algo.js routes)  ← CORRECTLY CONFIGURED
         ↓
    Query: SELECT ... FROM algo_performance_daily
         ↓
    Database Response ← PROBLEM IS HERE
    ├─ If AWS RDS: Data exists (loaders populate daily)
    └─ If Local:   Table doesn't exist or is empty
```

### Data Population (AWS)
```
EventBridge Schedule (4:45 PM ET)
         ↓
    Lambda: compute_performance_metrics
         ↓
    AWS RDS: Insert/Update algo_performance_daily table
         ↓
    Next dashboard refresh sees fresh data
```

## Verification Checklist

After applying the fix, verify:

- [ ] Configuration switched to AWS RDS
  ```powershell
  $env:DB_HOST  # Should show algo-db.cvjv6oql86ak.us-east-1.rds.amazonaws.com
  ```

- [ ] AWS credentials are current
  ```powershell
  aws sts get-caller-identity  # Should show valid credentials
  ```

- [ ] Database has tables
  ```bash
  python scripts/diagnose-dashboard-data.py  # Should show [OK] for tables
  ```

- [ ] Dashboard shows data
  - Navigate to Portfolio Dashboard
  - Should see portfolio value, performance metrics, etc.
  - Should NOT see "no data" or "API unavailable"

## Troubleshooting

### "API unavailable" error
→ Database configuration is wrong or AWS RDS unreachable
→ Run: `.\scripts\setup-database-config.ps1 -Show`
→ Check: DB_HOST should be algo-db...rds.amazonaws.com

### "Connection refused" to AWS RDS  
→ AWS security group may not allow your IP
→ Check: AWS Console → RDS → Security Groups
→ Or: AWS credentials may be expired
→ Run: `.\scripts\refresh-aws-credentials.ps1`

### Loaders haven't run (data still missing)
→ Loaders run on EventBridge schedule in production
→ They populate data into AWS RDS
→ For local database, you must run loaders manually

## Key Files Changed
- `scripts/setup-database-config.ps1` - NEW: Easy database switching
- `scripts/apply-database-schema.py` - NEW: Initialize local database
- `scripts/diagnose-dashboard-data.py` - NEW: Verify data availability
- `DASHBOARD_DATA_WIRING.md` - NEW: Architecture documentation

## Next Actions

**Immediate (Next 5 minutes):**
1. Run: `.\scripts\setup-database-config.ps1 -UseAWS`
2. Refresh AWS credentials if needed
3. Run: `.\scripts\setup-database-config.ps1 -Show`
4. Verify DB_HOST is AWS RDS endpoint

**Verify (Next 2 minutes):**
1. Refresh dashboard in browser
2. Check if data appears
3. If still missing, run: `python scripts/diagnose-dashboard-data.py`

**If Data Still Missing:**
1. Check AWS RDS is running (AWS Console)
2. Check if loaders have run recently (check AWS CloudWatch logs)
3. Run: `python loaders/load_algo_performance_daily.py` manually if needed

## Summary
- Your dashboard is configured correctly to call the right API endpoints
- The API routes exist and are properly implemented  
- The problem is **database configuration** (local vs AWS) and **data availability** (loaders haven't run)
- **FIX:** Switch to AWS RDS using the setup script, then verify data appears
