# Local Development Setup Guide

This guide explains how to run the same data loaders locally that power the AWS production environment.

## Prerequisites

- **PostgreSQL 12+** running locally on `localhost:5432`
- **Python 3.8+** with required dependencies (`pip install -r requirements.txt`)
- **Database created**: `createdb stocks`

## Quick Start

Run the complete local data loader pipeline:

```bash
cd /home/stocks/algo
./run_local_loaders.sh
```

This script runs all 7 production loaders in the correct dependency order with local database configuration.

## What Gets Loaded

The loader pipeline executes these 7 loaders in dependency order:

| # | Loader | Purpose | Depends On |
|---|--------|---------|-----------|
| 1 | `loadstocksymbols.py` | Stock symbol master list | (none) |
| 2 | `loadpricedaily.py` | Daily OHLCV price data | Stock symbols |
| 3 | `loadtechnicalsdaily.py` | Technical indicators | Price data |
| 4 | `loadinfo.py` | Company info & fundamentals | Stock symbols |
| 5 | `loaddailycompanydata.py` | Positioning data | Stock symbols |
| 6 | `loadsectordata.py` | Sector analysis & rankings | Price data |
| 7 | `loadstockscores.py` | Combined scoring | All previous |

## Custom Database Configuration

If your local database uses different credentials:

```bash
DB_HOST=localhost \
DB_PORT=5432 \
DB_USER=postgres \
DB_PASSWORD=mypassword \
DB_NAME=stocks \
./run_local_loaders.sh
```

Or set environment variables:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=password
./run_local_loaders.sh
```

## Individual Loader Execution

To run a single loader with local database:

```bash
USE_LOCAL_DB=true \
DB_HOST=localhost \
DB_PORT=5432 \
DB_USER=postgres \
DB_PASSWORD=password \
DB_NAME=stocks \
python3 loadstocksymbols.py
```

## Database Verification

Check that data loaded successfully:

```bash
# Count stock symbols
psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) FROM stock_symbols;"

# Check latest price data
psql -h localhost -U postgres -d stocks -c "SELECT * FROM price_daily LIMIT 5;"

# Verify sector performance loaded
psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) FROM sector_performance;"
```

## Key Architecture Details

### Local vs AWS Execution

All loaders support both AWS and local execution via the `USE_LOCAL_DB` environment variable:

- **`USE_LOCAL_DB=true`** → Uses local PostgreSQL on localhost:5432
- **Not set or `false`** → Reads credentials from AWS Secrets Manager

This means **the same exact code runs locally as in AWS production**.

### Database Configuration Logic

When `USE_LOCAL_DB=true`, loaders use these environment variables:
- `DB_HOST` (default: localhost)
- `DB_PORT` (default: 5432)
- `DB_USER` (default: postgres)
- `DB_PASSWORD` (default: password)
- `DB_NAME` (default: stocks)

### Connection Pooling

All loaders use connection pooling for efficient parallel processing:
- Min connections: 2
- Max connections: 10
- Max workers: 4 (CPU-aware)
- Batch size: 100 records

## Troubleshooting

### "Connection refused" error
- Verify PostgreSQL is running: `psql -h localhost -U postgres -d stocks -c "SELECT 1;"`
- Check credentials in environment variables
- Ensure database `stocks` exists: `psql -U postgres -l | grep stocks`

### "Table does not exist" errors
- First loader (`loadstocksymbols.py`) creates all tables
- Ensure you ran loaders in order - check dependencies above
- Run full pipeline: `./run_local_loaders.sh`

### Slow loader performance
- Check system resources: `top`, `free -h`
- Verify network connection for yfinance (price data)
- Loaders batch operations - processing time depends on stock count

### Data inconsistency between local and AWS
- Ensure you're using same stock symbols
- Verify time zones (all timestamps are UTC)
- Check that all 7 loaders completed successfully
- Run integrity check: Compare table row counts with AWS

## Development Workflow

### Before Development
```bash
# Start fresh database
dropdb stocks
createdb stocks

# Load all production data
./run_local_loaders.sh

# Verify backend connects to local DB
export USE_LOCAL_DB=true
cd webapp/lambda
node server.js
```

### During Development
```bash
# Frontend - separate terminal
cd webapp/frontend
npm run dev

# Backend - separate terminal
cd webapp/lambda
USE_LOCAL_DB=true node server.js

# Run tests
npm test
```

### After Development
```bash
# Run full loader pipeline to refresh test data
cd /home/stocks/algo
./run_local_loaders.sh

# Verify changes work with production data load
```

## File Structure

```
/home/stocks/algo/
├── run_critical_loaders.sh      # AWS production pipeline
├── run_local_loaders.sh         # Local development pipeline (this file runs)
│
├── loadstocksymbols.py          # 1. Symbol master list
├── loadpricedaily.py            # 2. Price OHLCV
├── loadtechnicalsdaily.py       # 3. Technical indicators
├── loadinfo.py                  # 4. Company fundamentals
├── loaddailycompanydata.py      # 5. Positioning data
├── loadsectordata.py            # 6. Sector analysis
├── loadstockscores.py           # 7. Combined scores
│
└── lib/
    ├── db.py                    # Database utilities
    ├── performance.py           # Calculation functions
    └── rankings.py              # Ranking utilities
```

## Important Notes

⚠️ **Identical Code Everywhere**
- Same loaders run in AWS production
- Use `./run_local_loaders.sh` to mirror production exactly
- No separate "development" loaders or special handling

✅ **Data Consistency**
- Local database structure matches AWS exactly
- All calculations are identical
- Results should be identical for same input data

🔄 **Regular Refresh**
- Run `./run_local_loaders.sh` regularly to keep data current
- Useful for feature development and testing

## Next Steps

- [Frontend Development](webapp/frontend/README.md)
- [Backend Development](webapp/lambda/README.md)
- [Database Schema](docs/SCHEMA.md)
