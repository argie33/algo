# Local Development Setup - Complete Guide

## Quick Start (2 minutes)

```bash
# 1. Clone and navigate
cd C:\Users\arger\code\algo

# 2. Start Docker Compose (includes new 60+ table schema)
docker-compose down -v          # Clean slate
docker-compose up -d            # Start postgres, redis, localstack

# 3. Wait for postgres to be healthy
docker-compose ps              # Watch for postgres "healthy" status

# 4. Verify schema created
docker-compose exec postgres psql -U stocks -d stocks -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public';"
# Expected: 60+

# 5. Done! Your local database now has all 60+ tables
```

## What Happens When You `docker-compose up`

1. **PostgreSQL container starts** with `init_db.sql` auto-mounted
2. **init_db.sql runs automatically** on first startup
3. **All 60+ tables created** (users, trades, positions, market data, etc.)
4. **TimescaleDB enabled** with 25+ hypertables
5. **Sample data inserted** (AAPL, MSFT, GOOGL)
6. **Ready for testing** in ~30 seconds

The `docker-compose.yml` already has this line:
```yaml
volumes:
  - ./init_db.sql:/docker-entrypoint-initdb.d/01-init.sql
```

So the schema deploys automatically. ✅

## Testing Locally

### 1. Verify Database

```bash
# Count tables (should be 60+)
docker-compose exec postgres psql -U stocks -d stocks \
  -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public';"

# List key tables
docker-compose exec postgres psql -U stocks -d stocks \
  -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LIMIT 20;"

# Check buy_sell_daily has all columns
docker-compose exec postgres psql -U stocks -d stocks \
  -c "\d buy_sell_daily" | grep -E "buylevel|stoplevel|rsi|adx"

# Check sample data
docker-compose exec postgres psql -U stocks -d stocks \
  -c "SELECT * FROM stock_symbols LIMIT 3;"
```

### 2. Test API Locally

```bash
# Start the Lambda API (from webapp/lambda directory)
cd webapp/lambda
npm install
npm start

# In another terminal, test endpoints
curl http://localhost:3001/health
curl http://localhost:3001/api/stocks?limit=5
curl http://localhost:3001/api/market/status
curl "http://localhost:3001/api/signals?limit=10"

# With auth (mock token)
curl -H "Authorization: Bearer test-token" http://localhost:3001/api/portfolio
```

### 3. Test Algo Locally

```bash
# Run the full 7-phase algo
python3 algo_run_daily.py

# You should see:
# ✅ Phase 1: Data freshness
# ✅ Phase 2: Circuit breakers
# ✅ Phase 3: Position monitoring
# ✅ Phase 4: Exit execution
# ✅ Phase 5: Signal generation
# ✅ Phase 6: Entry execution
# ✅ Phase 7: Reconciliation
```

### 4. Test Data Loaders Locally

```bash
# Load price data
python3 loadpricedaily.py

# Check it loaded
docker-compose exec postgres psql -U stocks -d stocks \
  -c "SELECT symbol, COUNT(*) as price_count FROM price_daily GROUP BY symbol LIMIT 5;"
```

## Development Workflow

### Adding/Modifying Schema Locally

If you need to change the schema:

1. **Edit init_db.sql**
   ```bash
   # Make your changes to init_db.sql
   # (add tables, columns, indexes, etc.)
   ```

2. **Reset local database**
   ```bash
   docker-compose down -v    # Delete old data
   docker-compose up -d      # Start fresh with new schema
   
   # Wait for postgres to be healthy
   sleep 10
   docker-compose exec postgres psql -U stocks -d stocks \
     -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public';"
   ```

3. **Test your changes**
   ```bash
   # Test API works
   npm start  # from webapp/lambda
   
   # Test algo works
   python3 algo_run_daily.py
   ```

4. **Commit when working**
   ```bash
   git add init_db.sql
   git commit -m "schema: Add new table X with columns Y, Z"
   ```

## Accessing the Database from Code

### Python (Algo)
```python
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='stocks',
    user='stocks',
    password=''  # empty password for local dev
)

cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("SELECT * FROM trades LIMIT 5;")
print(cur.fetchall())
```

### Node.js (Lambda/API)
```javascript
const { Pool } = require('pg');

const pool = new Pool({
  host: 'localhost',
  port: 5432,
  database: 'stocks',
  user: 'stocks',
  password: ''  // empty for local dev
});

const result = await pool.query('SELECT * FROM users LIMIT 5;');
console.log(result.rows);
```

### Command Line
```bash
# Connect directly
docker-compose exec postgres psql -U stocks -d stocks

# Then in psql:
\dt                           # List tables
SELECT * FROM stock_symbols;  # Query data
\q                            # Quit
```

## Common Tasks

### Clear All Data (Keep Schema)
```bash
docker-compose exec postgres psql -U stocks -d stocks \
  -c "TRUNCATE TABLE users CASCADE; TRUNCATE TABLE trades CASCADE;"
```

### Reset Everything (Delete Schema + Data)
```bash
docker-compose down -v
docker-compose up -d
```

### View Logs
```bash
docker-compose logs postgres   # Database logs
docker-compose logs redis      # Redis logs
docker-compose logs localstack # AWS simulation logs
```

### View Database with pgAdmin UI

```bash
# Enable UI
docker-compose --profile ui up -d

# Open browser
# http://localhost:5050
# Login: admin@example.com / admin
# Add server: postgres / 5432 / stocks / stocks (no password)
```

### View Redis with Redis Commander

```bash
# Enable UI
docker-compose --profile ui up -d

# Open browser
# http://localhost:8081
```

## Environment Variables

### Local Development (.env.local)

The Lambda/API reads `.env.local` for credentials:

```bash
# .env.local (NOT committed to git)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=stocks
POSTGRES_PASSWORD=
POSTGRES_DB=stocks

ALPACA_API_KEY=your_paper_trading_key
ALPACA_SECRET_KEY=your_paper_trading_secret
ALPACA_PAPER_TRADING=true

AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test      # LocalStack test key
AWS_SECRET_ACCESS_KEY=test  # LocalStack test key
```

## Troubleshooting

### "postgres is not healthy"

```bash
# Check postgres is running
docker-compose ps

# View postgres logs
docker-compose logs postgres

# Restart postgres
docker-compose restart postgres

# Wait for it
docker-compose exec postgres pg_isready -U stocks
```

### "relation does not exist"

```bash
# Check if schema initialized
docker-compose exec postgres psql -U stocks -d stocks \
  -c "SELECT COUNT(*) FROM pg_tables;"

# If 0 tables, schema didn't run. Reset:
docker-compose down -v
docker-compose up -d
```

### "password authentication failed"

```bash
# Check credentials in .env.local
# For local dev, password should be EMPTY (not 'password')

# Or connect directly:
docker-compose exec postgres psql -U stocks -d stocks
# (no password prompt needed)
```

### Port 5432 already in use

```bash
# Find what's using it
lsof -i :5432
# Kill it or use different port in docker-compose.yml
```

## Architecture

### Services Running Locally

```
┌─────────────────────────────────────────────────┐
│         Docker Compose Network                  │
├─────────────────────────────────────────────────┤
│                                                 │
│  📦 postgres:5432                               │
│     ├─ init_db.sql (60+ tables)                 │
│     ├─ Price data (price_daily, price_weekly)   │
│     ├─ Signals (buy_sell_daily)                 │
│     ├─ Trades (trades, positions)               │
│     ├─ Users & auth (users, user_api_keys)      │
│     ├─ Market data (technical_data_daily)       │
│     └─ Financial data (earnings, analysts)      │
│                                                 │
│  🔴 redis:6379                                  │
│     └─ In-memory cache, Bloom filters           │
│                                                 │
│  ☁️  localstack:4566                            │
│     └─ Simulates S3, Secrets, Lambda, etc.      │
│                                                 │
│  🖥️  pgadmin:5050 (optional UI)                 │
│  🖥️  redis-commander:8081 (optional UI)         │
│                                                 │
└─────────────────────────────────────────────────┘

Node.js Lambda (npm start)
   ↓ 
Connects to postgres:5432
   ↓
Queries all 60+ tables

Python Algo (algo_run_daily.py)
   ↓
Connects to postgres:5432
   ↓
Reads/writes positions, trades, signals
```

## Next Steps

1. ✅ **Schema in place** - init_db.sql has all 60+ tables
2. ✅ **docker-compose ready** - Auto-initializes schema
3. ⏭️ **Start docker-compose** - `docker-compose up -d`
4. ⏭️ **Verify tables** - Run query above
5. ⏭️ **Test API** - `npm start` from webapp/lambda
6. ⏭️ **Test algo** - `python3 algo_run_daily.py`
7. ⏭️ **Push to AWS** - GitHub Actions handles deployment

## Git Workflow

When working locally:

```bash
# Make changes to code
# ... edit files ...

# Test locally
npm start  # API
python3 algo_run_daily.py  # Algo

# When working, commit and push
git add .
git commit -m "feat: Add new endpoint or fix"
git push origin main

# GitHub Actions automatically:
# 1. Runs tests (ci-fast-gates.yml)
# 2. Deploys to AWS (deploy-webapp.yml, deploy-algo.yml, etc.)
```

---

**You're now set up to develop locally with the complete 60+ table schema!** 🚀
