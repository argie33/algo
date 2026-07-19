# Quick Start: Local Development Environment

**Status:** ✅ READY TO USE

## The Problem We Solved

You have:
- Orchestrator that runs 9 phases (but needs fresh data)
- 18 loaders that fetch data (but need scheduling)
- Dashboard that displays data (but nothing fresh locally without AWS)

**Solution:** Complete local dev coordinator that automates everything.

## Three Main Commands

### 1. Check Status
```bash
python dev_environment_setup.py --check
```
Verifies PostgreSQL, Dev Server, Dashboard, Data freshness.

### 2. Start Everything
```bash
python start_dev.py
```
- Starts Dev Server (if not running)
- Launches Dashboard (localhost:3000)
- Runs Orchestrator in background (every 1 hour)
- Everything coordinated automatically

### 3. Refresh Data
```bash
python run_dev_pipeline.py --morning      # 20 min
python run_dev_pipeline.py --eod          # 60 min
python run_dev_pipeline.py --computed     # 60 min
python run_dev_pipeline.py --full --fast  # 30 min (all, skip slow)
```

## Five Minute Setup

```bash
# Terminal 1: Verify everything is ready
python dev_environment_setup.py --check

# Terminal 2: Start services (dashboard opens automatically)
python start_dev.py
```

That's it. Dashboard is live with:
- Real market data
- Portfolio metrics
- Trading signals
- Circuit breaker status
- All updated automatically

## What Each Script Does

### `dev_environment_setup.py`
- Checks: PostgreSQL, Dev Server, Dashboard, Data freshness
- Sets: LOCAL_MODE environment variables
- Validates: System is ready to run

### `start_dev.py`
Main entry point. Launches:
1. PostgreSQL check (must be running)
2. Dev Server on localhost:3001 (if not already running)
3. Orchestrator Monitor (background, runs every 1 hour)
4. Dashboard on localhost:3000 (auto-opens, live data)

### `run_dev_pipeline.py`
Coordinates data loading and analysis:
1. Runs data loaders (Morning, EOD, Computed, or Full)
2. Runs orchestrator phases 1-9
3. Checks data freshness
4. Reports status

Modes:
- `--morning` - Prices + Technical (20 min)
- `--eod` - Financials (60 min)
- `--computed` - Scores + Signals (60 min)
- `--full` - Everything (2 hours)
- `--full --fast` - Skip slow loaders (30 min)
- `--watch SECONDS` - Auto-run on schedule

## How It Works

```
start_dev.py
├─ PostgreSQL (you must start separately)
├─ Dev Server (auto-start if needed)
├─ Orchestrator Monitor (background)
│  └─ Runs run_dev_pipeline.py --watch 3600
│     └─ Runs loaders → orchestrator → health check
└─ Dashboard (opens automatically)
   └─ Reads fresh data from PostgreSQL
```

## Environment Variables (Auto-Set)

```
LOCAL_MODE=true                # Use local mode (no AWS)
ENVIRONMENT=development        # Dev error handling
SKIP_ORCHESTRATOR_LOCK=true    # No DynamoDB needed
```

Saved to `.env.local` for persistence.

## Local Mode Features

✅ **Enabled:**
- Dashboard displays fresh data
- Orchestrator runs phases 1-9
- Loaders refresh data
- Auto-health checks
- Local-only development

❌ **Disabled:**
- Trading execution (Phase 8 skipped)
- AWS credentials required
- DynamoDB locking
- Lambda invocations
- EventBridge scheduling

Safe for development - trading is disabled.

## Common Tasks

### Refresh prices (before market open)
```bash
python run_dev_pipeline.py --morning
```

### Full data refresh (testing)
```bash
python run_dev_pipeline.py --full --fast
```

### Check what's stale
```bash
python check_system_health.py
```

### Just run orchestrator (assume data is fresh)
```bash
python scripts/run_local_orchestrator.py
```

### View orchestrator status
```bash
cd loaders && python ../scripts/run_local_orchestrator.py
```

## Data Pipeline Timing

**Morning (2 AM ET):**
- Prices (5-10 min)
- Technical indicators (15-25 min)

**Reference (9:15 AM ET):**
- Market constituents (< 1 min)
- Economic data (1-2 min)

**EOD (4 PM ET):**
- Financial statements (20-30 min)
- Metrics & fundamentals (30 min)

**Computed (7 PM ET):**
- Scores, signals, risk (60 min)

Can run manually anytime with `run_dev_pipeline.py`.

## Architecture Diagram

```
You
 ↓
start_dev.py (ENTRY POINT)
 ├─ Checks PostgreSQL ✓
 ├─ Starts Dev Server → localhost:3001 ✓
 ├─ Starts Orchestrator Monitor (background)
 │  └─ Every 1 hour: run_dev_pipeline.py
 │     └─ Loaders → Orchestrator → Health Check
 └─ Opens Dashboard → localhost:3000
    └─ Reads PostgreSQL (fresh data)
       ├─ Prices (real-time)
       ├─ Scores & signals
       ├─ Portfolio metrics
       ├─ Circuit breakers
       └─ Risk metrics
```

## Troubleshooting

### "PostgreSQL connection refused"
```bash
# PostgreSQL must be running
# Start it: psql -U stocks -d stocks
# Or check if service is running
```

### "Dev Server not responding"
```bash
# start_dev.py should auto-start it
# Or manually: python lambda/api/dev_server.py
```

### "Dashboard shows no data"
```bash
# Data loaders haven't run yet
python run_dev_pipeline.py --morning
# Wait 20-30 minutes, then refresh dashboard
```

### "Orchestrator keeps stopping"
```bash
# Check for errors: python scripts/run_local_orchestrator.py
# Usually: Missing data or stale prices
```

### "Loader hangs/timeout"
```bash
# load_yfinance_snapshot.py can take 45 minutes
# Use --fast to skip it: python run_dev_pipeline.py --full --fast
```

## Next Steps

1. **First Time:**
   ```bash
   python dev_environment_setup.py
   python start_dev.py --refresh-data
   ```

2. **Daily:**
   ```bash
   python start_dev.py
   # Check dashboard for fresh data
   ```

3. **Manual Refresh:**
   ```bash
   python run_dev_pipeline.py --morning
   # Or just run loaders: cd loaders && python load_prices.py
   ```

4. **Full Refresh (Testing):**
   ```bash
   python run_dev_pipeline.py --full --fast
   ```

## See Also

- `DEV_ENVIRONMENT.md` - Full documentation
- `LOCAL_LOADER_GUIDE.md` - Detailed loader info
- `scripts/run_local_orchestrator.py` - Direct orchestrator runner
- `check_system_health.py` - Data staleness checker
- `dashboard.py --local` - Dashboard (auto-started by start_dev.py)

---

**You're ready!** Run `python start_dev.py` and the system handles everything else.
