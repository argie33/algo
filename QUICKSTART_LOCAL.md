# Quick Start: Local Development Setup

Last updated: 2026-07-17 (Session 203)

Get the system running locally in 10 minutes. System is fully functional without AWS.

---

## Prerequisites (One-Time Setup)

### 1. Clone Repo
```bash
git clone https://github.com/edgebrookelabs/algo.git
cd algo
```

### 2. Install Python & Dependencies
```bash
# Requires Python 3.11+
python --version

# Install in editable mode (includes dev dependencies)
pip install -e ".[dev]"
```

### 3. Start PostgreSQL
```bash
# macOS (via Homebrew)
brew services start postgresql

# Linux (via apt)
sudo systemctl start postgresql

# Docker
docker run --rm -d -p 5432:5432 \
  -e POSTGRES_DB=stocks \
  -e POSTGRES_USER=stocks \
  -e POSTGRES_PASSWORD=stocks \
  postgres:16

# Windows (WSL2 + Docker)
# Same Docker command as above
```

### 4. Initialize Database (One-Time)
```bash
python scripts/apply-database-schema.py
```

This creates all tables and indices. Safe to run multiple times (uses CREATE TABLE IF NOT EXISTS).

---

## 3-Minute Startup (Recommended)

**Use the unified startup script — it handles everything:**

```bash
python start_dashboard_dev.py
```

This automatically:
- ✅ Detects if dev_server is running (localhost:3001)
- ✅ Starts dev_server if needed (waits for readiness)
- ✅ Starts dashboard
- ✅ Auto-refreshes data every 30s
- ✅ Cleans up on exit (Ctrl+C)

**Optional: Set custom refresh interval**
```bash
python start_dashboard_dev.py -w 60    # 60-second refresh
```

Done. Dashboard opens automatically. See your portfolio, positions, metrics.

---

## Manual Startup (If Preferred)

If you want more control, start each component separately.

### Terminal 1: Start API Dev Server
```bash
python lambda/api/dev_server.py
```

Wait for:
```
[INFO] Starting API dev server on http://localhost:3001
```

The dev server provides all API endpoints (portfolio, circuit breakers, market regime, etc).

### Terminal 2: Start Dashboard
```bash
python dashboard.py
```

Or with auto-refresh every 30s:
```bash
python dashboard.py -w 30
```

**IMPORTANT:** Dashboard auto-detects localhost ONLY if dev_server is already running on Terminal 1.
If you skip Terminal 1 or dev_server stops, dashboard will fail with "data not available". Always ensure Terminal 1 is running first.

### Optional Terminal 3: Refresh Data

When you need fresh data (prices, technical indicators, metrics):
```bash
python3 scripts/run_local_orchestrator.py --morning
```

This runs:
- Load prices
- Compute technical indicators
- Calculate market exposure
- Refresh all dashboards

---

## First Run: Check System Health

Before diving in, verify everything is connected:

```bash
python check_system_health.py
```

Shows:
- ✓ SUCCESS: Database connected, data loaded
- ✓ SUCCESS: Dev server running
- ✓ SUCCESS: Orchestrator executed
- ✓ SUCCESS: All imports working

If you see ✗ errors, fix them before proceeding (see DASHBOARD_TROUBLESHOOTING.md).

---

## Alpaca Credentials (For Phase 8 Trading)

**Credentials are automatically loaded from database. No .env files needed.**

Credentials are stored in `algo_config` table and loaded before each run:
- `alpaca_api_key` → APCA_API_KEY_ID
- `alpaca_api_secret` → APCA_API_SECRET_KEY  
- `alpaca_base_url` → APCA_API_BASE_URL

**Current setup:** Alpaca credentials are already configured in database. They persist across all runs automatically.

**If credentials change:** Update the database:
```bash
python -c "
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()
cur.execute('UPDATE algo_config SET value = %s WHERE key = %s', 
            ('YOUR_NEW_KEY', 'alpaca_api_key'))
cur.execute('UPDATE algo_config SET value = %s WHERE key = %s',
            ('YOUR_NEW_SECRET', 'alpaca_api_secret'))
conn.commit()
"
```

---

## Common Tasks

### Refresh Data (Prices + Indicators)
```bash
python3 scripts/run_local_orchestrator.py --morning
```

**Note:** Alpaca credentials are automatically loaded from database before running.

### Refresh Everything (All Three Pipelines)
```bash
python3 scripts/run_local_orchestrator.py --run-all
```

Runs:
- Morning: Prices + technical + market health
- Afternoon: Technical + signals + sentiment
- Evening: Metrics + performance

### Check Data Freshness
```bash
python scripts/monitor_data_staleness.py
```

Shows how old each data table is. Exit code = number of stale tables.

### Run All Tests
```bash
python -m pytest tests/ -q
```

Expected: 1082 passing (Session 203).

### Check Code Quality
```bash
# Type checking (mypy strict)
python -m mypy dashboard/ lambda/api/ --strict

# Linting (ruff)
python -m ruff check .

# Format code
python -m ruff format .
```

### Database Queries
```bash
# Connect directly
psql -U stocks -d stocks

# Example queries
SELECT COUNT(*) FROM stock_prices_daily;
SELECT COUNT(*) FROM technical_data_daily;
SELECT * FROM algo_portfolio_snapshots ORDER BY created_at DESC LIMIT 1;
```

---

## Dashboard Features (What You Can Do)

### Portfolio View
- **Positions:** Open positions with entry price, current price, PnL
- **Allocation:** Sector/industry breakdown by percent
- **Cash:** Available cash + buying power

### Performance
- **PnL:** Daily + cumulative unrealized PnL
- **Trades:** Win/loss ratio, average trade size
- **Metrics:** Sharpe ratio, max drawdown, Sortino ratio

### Market
- **VIX:** Current volatility level + trend
- **Market Regime:** Current stage (1-4, 1=bullish, 4=bearish)
- **Exposure:** Sector/industry allocation limits

### Circuit Breakers
- **Status:** 8 automatic risk gates
- **Triggers:** Which ones are active (if any)
- **Recovery:** When will they re-enable (auto-recovery timer)

### Technical Analysis
- **Signals:** BUY/SELL candidates ranked by composite score
- **Quality Scores:** Fundamental quality + growth + value metrics
- **Completeness:** % of data available for each symbol

---

## Auto-Refresh Options

### No Auto-Refresh (Manual Only)
```bash
python dashboard.py
# Refresh with Ctrl+R or F5
```

### Auto-Refresh Every 30s (Default)
```bash
python dashboard.py -w 30
```

### Auto-Refresh Every 5s (Fast, Noisy)
```bash
python dashboard.py -w 5
```

### Auto-Refresh Every 60s (Slow, Low Resource)
```bash
python dashboard.py -w 60
```

---

## AWS vs Local Mode (Auto-Detection)

Dashboard **automatically detects** which mode to use:

| Condition | Mode | API |
|-----------|------|-----|
| Dev server running on localhost:3001 | Local | Dev API (localhost:3001) |
| Dev server not running, AWS creds available | AWS | Lambda API Gateway |
| Dev server not running, no AWS creds | Error | (Cannot connect) |

### Force Local Mode
```bash
python dashboard.py --local
# Fails if dev_server not running
```

### Force AWS Mode (If Credentials Available)
```bash
python dashboard.py --aws
# Uses Lambda endpoint + Cognito auth
```

---

## Troubleshooting

### "Connection refused on localhost:3001"
→ Dev server not running. Start Terminal 1: `python lambda/api/dev_server.py`

### "Data not available" on all panels
→ Run: `python check_system_health.py` (full diagnostics)

### Database connection error
→ PostgreSQL not running. Start it: `brew services start postgresql` (macOS)

### "No module named 'dashboard'"
→ Reinstall package: `pip install -e .`

### Tests fail with "pytest teardown error"
→ Already fixed in Session 203. Run `git pull origin main` to get latest.

### Need more help?
→ See `DASHBOARD_TROUBLESHOOTING.md` (full troubleshooting guide)
→ See `steering/COMMON_OPERATIONS.md` (broader operations reference)

---

## Next Steps

1. **Data Exploration:** Dashboard shows live portfolio + market data
2. **Manual Trades:** Use Alpaca paper trading account (configured by default)
3. **Run Orchestrator:** `python3 scripts/run_local_orchestrator.py --morning` to execute trading logic
4. **Monitor Positions:** Watch dashboard as trades execute (every 5 min when orchestrator runs)
5. **Deploy to AWS:** When ready, see `steering/OPERATIONS.md` for production setup

---

## File Structure (Key Directories)

```
algo/
├── dashboard.py            # Main dashboard (run this)
├── start_dashboard_dev.py  # Unified startup script (recommended)
├── check_system_health.py  # System health check
├── lambda/
│   └── api/
│       └── dev_server.py   # Local API server (Terminal 1)
├── scripts/
│   ├── run_local_orchestrator.py   # Local trading engine
│   ├── monitor_data_staleness.py   # Check data freshness
│   └── apply-database-schema.py    # Database init
├── algo/
│   ├── algo_orchestrator.py        # Trading logic
│   └── circuit_breaker.py          # Risk gates
├── loaders/
│   └── load_*.py           # Data loaders (prices, technical, etc)
└── steering/
    ├── GOVERNANCE.md       # Architecture + rules
    ├── OPERATIONS.md       # Deployment + CI/CD
    ├── DATA_LOADERS.md     # Loader orchestration
    └── COMMON_OPERATIONS.md # Troubleshooting reference
```

---

## Development Workflow

### Edit Code
```bash
# Edit any Python file
# Tests auto-run on save if using IDE (VS Code, PyCharm)
```

### Run Tests
```bash
python -m pytest tests/test_dashboard.py -v
```

### Check Types & Linting
```bash
python -m mypy dashboard/ --strict
python -m ruff check .
```

### Commit Changes
```bash
git add .
git commit -m "feat: Add cool feature"
# Pre-commit hooks run automatically (type check, lint, test)
```

### Push to Main
```bash
git push origin main
# GitHub Actions auto-deploys to AWS (if credentials available)
```

---

## Common Configuration

### Change Trading Thresholds
```sql
UPDATE algo_config 
SET value = '75' 
WHERE key = 'signal_score_threshold';

-- Takes effect on next orchestrator run
```

### Disable Circuit Breakers (Emergency Only)
```sql
UPDATE algo_config 
SET value = 'false' 
WHERE key = 'orchestrator_halt_enabled';
```

### Adjust Positions Limit
```sql
UPDATE algo_config 
SET value = '10' 
WHERE key = 'max_open_positions';
```

See `steering/OPERATIONS.md` for all configurable parameters.

---

## Helpful Commands

```bash
# Test everything (all tests)
python -m pytest tests/ -q

# Test specific file
python -m pytest tests/test_orchestrator.py -v

# Run only passing tests (skip xfail)
python -m pytest tests/ -v --runxfail

# Check code coverage
python -m pytest tests/ --cov=algo --cov=dashboard

# Format all code
python -m ruff format .

# Type check (mypy)
python -m mypy algo/ lambda/api/ dashboard/ --strict

# Lint (ruff)
python -m ruff check .

# Start database
brew services start postgresql   # macOS
docker run ... postgres:16       # Docker

# Connect to database
psql -U stocks -d stocks

# Backup database
pg_dump -U stocks stocks > backup.sql

# Restore database
psql -U stocks stocks < backup.sql

# Monitor real-time logs
tail -f logs/dashboard.log

# Check orchestrator status
python3 -c "from scripts.run_local_orchestrator import run_orchestrator; run_orchestrator()"
```

---

That's it! You're ready to develop. 🚀
