# Local Development Environment Guide

Complete setup for running the algo system locally without AWS. Everything is automated and coordinates together.

## Quick Start (3 commands)

```bash
# 1. Check system is ready
python dev_environment_setup.py --check

# 2. Start everything (API + Dashboard + Background Orchestrator)
python start_dev.py

# 3. (Optional) Manually refresh data
python run_dev_pipeline.py --full --fast
```

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  LOCAL DEV ENVIRONMENT                    │
├──────────────────────────────────────────────────────────┤
│                                                            │
│  start_dev.py                                             │
│  ├─ PostgreSQL (required, must be running)               │
│  ├─ Dev Server (lambda/api) on localhost:3001            │
│  ├─ Dashboard (automatic, localhost:3000)                │
│  └─ Orchestrator Monitor (background, runs every 1h)     │
│                                                            │
│  Manual operations:                                       │
│  ├─ run_dev_pipeline.py --morning    (prices, technical) │
│  ├─ run_dev_pipeline.py --eod        (financials)        │
│  ├─ run_dev_pipeline.py --computed   (scores, signals)   │
│  └─ run_dev_pipeline.py --full       (everything)        │
│                                                            │
│  Status/Diagnostics:                                      │
│  ├─ check_system_health.py           (data freshness)    │
│  ├─ dev_environment_setup.py --check (service status)    │
│  └─ python -c "import psycopg2; ..."  (DB connectivity)  │
│                                                            │
└──────────────────────────────────────────────────────────┘
```

## Scripts Overview

### 1. `dev_environment_setup.py` - Environment Check
Verifies all prerequisites and sets LOCAL_MODE environment variables.

```bash
python dev_environment_setup.py              # Setup + verify
python dev_environment_setup.py --check      # Status only
```

**Checks:**
- PostgreSQL connectivity
- Dev Server availability
- Data freshness
- Dashboard module imports

### 2. `start_dev.py` - Unified Startup
Launches all services and coordinates them. This is your main entry point.

```bash
python start_dev.py                          # Start all services + dashboard
python start_dev.py --check-only             # Status check (no startup)
python start_dev.py --no-dashboard           # Start services, no dashboard
python start_dev.py --refresh-data           # Refresh data, then start
```

**Starts:**
1. Dev Server (if not running)
2. Orchestrator Monitor (background)
3. Dashboard (auto-opens, localhost:3000)

### 3. `run_dev_pipeline.py` - Data Pipeline Coordinator
Runs loaders + orchestrator + health check on schedule.

```bash
# Manual runs
python run_dev_pipeline.py --morning         # Prices + Technical (20 min)
python run_dev_pipeline.py --eod             # Financials + Metrics (60 min)
python run_dev_pipeline.py --computed        # Scores + Signals (60 min)
python run_dev_pipeline.py --full            # All loaders (2 hours)
python run_dev_pipeline.py --full --fast     # Skip slow loaders (30 min)

# Automated runs (background)
python run_dev_pipeline.py --watch 3600      # Every 1 hour
python run_dev_pipeline.py --watch 300       # Every 5 minutes (testing)
```

**Pipeline Stages:**
1. Run data loaders (parallelizable)
2. Run orchestrator phases 1-9
3. Check data freshness
4. Report status

## Daily Workflow

### Option A: Fully Automated (Recommended)
```bash
# Terminal 1: Run once, everything auto-manages
python start_dev.py
# Dashboard opens automatically
# Orchestrator runs in background every 1 hour
# Loaders refresh automatically on schedule
```

### Option B: Manual Control
```bash
# Terminal 1: Start services
python start_dev.py --no-dashboard

# Terminal 2: Refresh data when needed
python run_dev_pipeline.py --morning        # Run morning loaders
python run_dev_pipeline.py --eod            # Run EOD loaders

# Terminal 3: Open dashboard
python dashboard.py --local -w 30           # Auto-refresh every 30s
```

### Option C: Development/Testing
```bash
# Quick full refresh (skip slow loaders)
python run_dev_pipeline.py --full --fast    # 30 min instead of 2 hours

# Just run orchestrator (assume data is fresh)
python scripts/run_local_orchestrator.py

# Just check what's stale
python check_system_health.py
```

## Data Pipelines

### Morning Pipeline (2 AM ET)
Prices + technical indicators needed for daily trading signals.
```bash
python run_dev_pipeline.py --morning
```
**Loaders:**
- `load_prices.py` (5-10 min) - Alpaca prices
- `load_technical_indicators.py` (15-25 min) - SMA, RSI, ATR

**Data Updated:**
- `price_daily`
- `etf_price_daily`
- `technical_data_daily`

### EOD Pipeline (4 PM ET)
Financial statements + fundamental metrics.
```bash
python run_dev_pipeline.py --eod
```
**Loaders:**
- `load_market_health_daily.py` (2-5 min)
- `load_financial_statements.py` (20-30 min)
- `load_quality_growth_metrics.py` (10-15 min)
- `load_yfinance_derived_metrics.py` (5-10 min)
- `load_yfinance_snapshot.py` (30-45 min) ⚠️ SLOW

**Data Updated:**
- `financial_data_*`
- `quality_metrics`
- `growth_metrics`
- `value_metrics`

### Computed Pipeline (7 PM ET)
Aggregated scores and signals.
```bash
python run_dev_pipeline.py --computed
```
**Loaders:**
- `load_market_exposure_daily.py` (2-5 min)
- `load_stock_scores.py` (10-15 min)
- `load_buy_sell_daily.py` (5-10 min)
- `load_trend_analysis.py` (30-45 min)
- `load_risk_metrics_daily.py` (5-10 min)

**Data Updated:**
- `stock_scores`
- `buy_sell_daily`
- `trend_template_data`
- `algo_risk_daily`

### Full Pipeline
Everything at once (2 hours).
```bash
python run_dev_pipeline.py --full
python run_dev_pipeline.py --full --fast    # Skip yfinance (30 min)
```

## Current Data Status

Check what's fresh/stale:
```bash
python check_system_health.py
```

**Recent Status:**
- ✅ `price_daily` - Fresh (prices loader)
- ✅ `stock_scores` - Fresh (orchestrator + loader)
- ✅ `technical_data_daily` - Fresh (orchestrator + loader)
- 🔴 `etf_price_daily` - Stale? Run: `cd loaders && python load_prices.py`
- 🔴 `market_exposure_daily` - Stale? Run: `cd loaders && python load_market_exposure_daily.py`

## Environment Variables

Automatically set by `dev_environment_setup.py`:

```bash
LOCAL_MODE=true                    # Enables local-only behavior
ENVIRONMENT=development            # Dev error handling
SKIP_ORCHESTRATOR_LOCK=true        # No DynamoDB locking needed
```

Saved to `.env.local` for persistence.

## Troubleshooting

### "PostgreSQL connection refused"
```bash
# Check if PostgreSQL is running
psql -U stocks -d stocks

# If not running, start it:
# Windows: Start PostgreSQL service
# macOS: brew services start postgresql
# Linux: sudo systemctl start postgresql
```

### "Dev Server not responding"
```bash
# Start manually in another terminal
python lambda/api/dev_server.py

# Should show: "Starting API dev server on http://localhost:3001"
```

### "Dashboard shows 'Data not available'"
```bash
# Data loaders haven't run yet
python run_dev_pipeline.py --full --fast

# Or run specific loaders
cd loaders && python load_prices.py
cd loaders && python load_stock_scores.py
```

### "Orchestrator keeps stopping/restarting"
```bash
# Check for orphaned processes
ps aux | grep orchestrator

# Check logs (if running interactively)
python scripts/run_local_orchestrator.py
```

### "Loader hangs (seems stuck)"
```bash
# Most loaders timeout at 10 minutes. If stuck longer:
# • load_yfinance_snapshot.py is known slow (30-45 min)
# • Use --fast flag to skip it

python run_dev_pipeline.py --full --fast
```

## Performance Profile

| Operation | Time | When to Use |
|-----------|------|-------------|
| Morning pipeline | 20 min | Before market opens |
| EOD pipeline | 60 min | After market close |
| Computed pipeline | 60 min | Evening (7 PM) |
| Full refresh (with slow) | 2 hours | Rare, when all data needed |
| Full refresh (--fast) | 30 min | Skip yfinance snapshot |
| Orchestrator only | 7-10 min | Uses existing data |
| Dashboard startup | 2-3 min | Auto-refresh every 30s |

## Next Steps

1. **First Time Setup:**
   ```bash
   python dev_environment_setup.py
   python start_dev.py --refresh-data
   ```

2. **Daily Development:**
   ```bash
   python start_dev.py
   # Dashboard opens, everything auto-manages
   ```

3. **Manual Data Refresh:**
   ```bash
   python run_dev_pipeline.py --morning   # If prices stale
   python run_dev_pipeline.py --full --fast  # Full refresh (30 min)
   ```

4. **Debugging:**
   ```bash
   python check_system_health.py          # See what's stale
   python dev_environment_setup.py --check  # See service status
   ```

## Environment vs AWS

| Feature | Local Dev | AWS Production |
|---------|-----------|---|
| Database | PostgreSQL on localhost | AWS RDS |
| API | Dev server on localhost:3001 | Lambda + API Gateway |
| Scheduling | Manual or Python scheduler | EventBridge Scheduler |
| Trading | Skipped (LOCAL_MODE) | Alpaca + Lambda execution |
| Locking | DynamoDB errors ignored | DynamoDB orchestrator_locks |
| Credentials | Not required | AWS Secrets Manager |

Local mode is **safe**: trading is disabled, distributed locks are skipped, AWS credentials are optional.

