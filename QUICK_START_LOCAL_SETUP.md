# Quick Start — Get Running Locally in 10 Minutes

This is the **fast path** to get your local development environment working.

---

## Prerequisites

You must have:
- **Docker** & **Docker Compose** installed
- **Python 3.9+**
- **Git**
- Access to your Alpaca paper trading API keys

---

## 5 Steps to Get Running

### Step 1: Set Up Environment (2 minutes)

```bash
# Copy template to local config
cp .env.local.example .env.local

# Edit with your values
# IMPORTANT: Change at least these:
#   DB_PASSWORD=something-secure
#   APCA_API_KEY_ID=your-paper-key
#   APCA_API_SECRET_KEY=your-paper-secret
```

### Step 2: Start PostgreSQL (1 minute)

```bash
docker-compose -f docker-compose.local.yml up -d
```

Wait for it to be ready:
```bash
docker-compose -f docker-compose.local.yml logs postgres | grep "ready to accept"
```

### Step 3: Create Database Schema (1 minute)

```bash
python init_database.py
```

Verify tables created:
```bash
docker-compose -f docker-compose.local.yml exec postgres psql -U stocks -d stocks -c "\dt algo_*"
```

Should show: `algo_tca`, `algo_performance_daily`, `algo_risk_daily`, etc.

### Step 4: Test Orchestrator (3 minutes)

```bash
python algo_orchestrator.py --dry-run
```

Should complete all 7 phases with no errors.

### Step 5: Verify Database (1 minute)

```bash
# Check that trades were recorded
docker-compose -f docker-compose.local.yml exec postgres psql -U stocks -d stocks -c "SELECT COUNT(*) FROM algo_positions;"

# Check that TCA records were created
docker-compose -f docker-compose.local.yml exec postgres psql -U stocks -d stocks -c "SELECT COUNT(*) FROM algo_tca;"

# Check performance metrics
docker-compose -f docker-compose.local.yml exec postgres psql -U stocks -d stocks -c "SELECT * FROM algo_performance_daily LIMIT 1;"
```

---

## That's It!

You now have:
- ✓ PostgreSQL running locally
- ✓ All algo tables created
- ✓ Orchestrator executing end-to-end
- ✓ Data being recorded to database

---

## What to Do Next

### Option A: Development & Testing
```bash
# Make code changes
vi algo_orchestrator.py

# Test changes
python -m pytest tests/

# Run orchestrator again
python algo_orchestrator.py --dry-run
```

### Option B: Load Historical Data
```bash
# Load 1+ year of price data (if you have a loader)
python load_historical_prices.py --years 3 --symbols "SPY,QQQ"

# This populates algo_portfolio_snapshots for metrics
```

### Option C: Access Database Directly
```bash
# Via command line
psql -h localhost -U stocks -d stocks

# Via pgAdmin web UI
# Go to http://localhost:5050
# Login: admin@stocks.local / admin
```

### Option D: Paper Trading Mode
```bash
# Edit .env.local
# Set: EXECUTION_MODE=paper
# Set: ORCHESTRATOR_DRY_RUN=false

# Run in paper trading mode
python algo_orchestrator.py
```

---

## Stopping Services

When done:
```bash
# Stop but keep data
docker-compose -f docker-compose.local.yml down

# Or stop and delete all data (fresh start)
docker-compose -f docker-compose.local.yml down -v
```

---

## Troubleshooting

### Docker not found
Install Docker Desktop from https://www.docker.com/products/docker-desktop

### Port 5432 in use
Change in docker-compose.local.yml:
```yaml
ports:
  - "5432:5432"  # Change first number to something else (e.g., "5433:5432")
```

### psql command not found
Use docker-compose instead:
```bash
docker-compose -f docker-compose.local.yml exec postgres psql -U stocks -d stocks -c "SELECT 1;"
```

### Python import errors
Reinstall dependencies:
```bash
pip install -r requirements.txt
```

### Orchestrator hangs
Check database is responding:
```bash
docker-compose -f docker-compose.local.yml logs postgres
```

---

## Full Documentation

For detailed information, see:
- **SETUP_LOCAL_DEVELOPMENT.md** — Complete step-by-step guide
- **ARCHITECTURE_AND_IAC_GUIDE.md** — IaC principles & architecture
- **THE_RIGHT_WAY_SUMMARY.md** — Why this approach is correct

---

**Ready?** Start with **Step 1** above. You'll have everything running in 10 minutes.
