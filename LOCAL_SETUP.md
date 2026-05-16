# Local Development Setup (Windows - No Docker/WSL)

## Prerequisites

1. **PostgreSQL 16+ on Windows**
   - Download: https://www.postgresql.org/download/windows/
   - Install with default settings
   - Remember the postgres password you set during install
   - Default: `postgres` user, port `5432`

2. **Python 3.10+**
   - Already have it (verified during setup)

## Step 1: Create Local Database

```bash
# Open PostgreSQL command prompt or use psql directly:
psql -U postgres

# In psql, run:
CREATE DATABASE stocks;
CREATE USER stocks WITH PASSWORD 'postgres';
GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;
\q
```

## Step 2: Initialize Database Schema

```bash
# In algo/ directory:
python3 init_database.py
# Sets: DB_HOST=localhost, DB_USER=stocks, DB_NAME=stocks, DB_PASSWORD=postgres
```

**Verify:**
```bash
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols;"
# Should return: 0 (no data yet)
```

## Step 3: Load Data

```bash
# Run all loaders in dependency order:
python3 run-all-loaders.py

# Or run by tier:
python3 loadstocksymbols.py                    # Tier 0 - symbols
python3 loadpricedaily.py                      # Tier 1 - prices (takes ~5 min)
python3 loadbuyselldaily.py                    # Tier 3 - signals
python3 load_algo_metrics_daily.py              # Tier 4 - metrics
```

## Step 4: Verify Data

```bash
psql -h localhost -U stocks -d stocks << EOF
SELECT 'Symbols' as table_name, COUNT(*) as count FROM stock_symbols
UNION ALL
SELECT 'Prices', COUNT(*) FROM price_daily
UNION ALL
SELECT 'Signals', COUNT(*) FROM buy_sell_daily
UNION ALL
SELECT 'Metrics', COUNT(*) FROM algo_metrics_daily;
EOF
```

**Expected output:**
```
table_name |  count
-----------+--------
Symbols    | 50000+
Prices     | 1000000+
Signals    | 50000+
Metrics    | 5000+
```

## Step 5: Test Locally

```bash
# Test orchestrator
python3 algo_orchestrator.py --mode paper --dry-run
# Should complete all 7 phases without errors

# Or run specific tests
python3 -m pytest tests/ -v
```

## Connection String for Apps

```
postgresql://stocks:postgres@localhost:5432/stocks
```

## Troubleshooting

**psql: command not found**
- Add PostgreSQL bin to PATH: `C:\Program Files\PostgreSQL\16\bin`
- Or use full path: `"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres`

**Connection refused**
- Check PostgreSQL service is running: `services.msc` → PostgreSQL → Start

**Database already exists**
- Drop and recreate: `DROP DATABASE stocks;` in psql, then re-run init_database.py

**Out of memory during loaders**
- Run one loader at a time instead of `run-all-loaders.py`
- Or increase max_connections in PostgreSQL config
