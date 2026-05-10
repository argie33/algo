# Local Development Setup Guide

Spin up entire platform locally with **Docker Compose** in 5 minutes. Matches production architecture.

## Quick Start

### 1. Start All Services
```bash
# Core services (postgres, redis, localstack)
docker-compose up -d

# Or with UI tools (pgAdmin, Redis Commander)
docker-compose --profile ui up -d

# Check health
docker-compose ps
```

### 2. Verify Database
```bash
# Connect to database
psql -h localhost -U stocks -d stocks

# Or via pgAdmin: http://localhost:5050
# (admin@example.com / admin)
```

### 3. Verify Redis
```bash
# Connect to Redis
redis-cli -h localhost

# Or via Redis Commander: http://localhost:8081
```

### 4. Test a Loader
```bash
export DB_HOST=localhost
export DB_USER=stocks
export DB_PASSWORD=''
export REDIS_URL=redis://localhost:6379

python3 loadpricedaily.py --symbols AAPL,MSFT --parallelism 2
```

## What's Running

### Core Services

| Service | Port | Purpose | Volume |
|---------|------|---------|--------|
| **PostgreSQL** | 5432 | Price data, signals, metadata | postgres_data |
| **Redis** | 6379 | Bloom filter dedup, caching | redis_data |
| **LocalStack** | 4566 | Mock AWS (S3, Lambda, Secrets) | ephemeral |

### Optional UI Tools (--profile ui)

| Tool | Port | Purpose |
|------|------|---------|
| **pgAdmin** | 5050 | Database UI |
| **Redis Commander** | 8081 | Redis UI |

## Common Tasks

### View Database Schema
```bash
# Via psql
psql -h localhost -U stocks -d stocks -c "\dt"

# Via pgAdmin
http://localhost:5050
→ Add New Server
  Host: postgres
  Username: stocks
  (no password)
```

### View Watermarks
```bash
psql -h localhost -U stocks -d stocks -c "
  SELECT loader, symbol, watermark, rows_loaded, last_run_at
  FROM loader_watermarks
  LIMIT 20;"
```

### View Bloom Filter Stats
```bash
redis-cli -h localhost
> INFO memoryusage
> KEYS dedup:*
```

### Reset Database
```bash
# Stop containers
docker-compose down

# Remove database volume (WARNING: deletes data)
docker volume rm algo_postgres_data

# Restart
docker-compose up -d postgres
# Database will reinitialize from init_db.sql
```

### Run Tests
```bash
# Unit tests
pytest tests/ -v

# Loader integration test
python3 test-watermark-incremental.py

# Alpaca loader test
python3 test-alpaca-loader.py --quick

# Lambda wrapper test (locally)
python3 lambda_loader_wrapper.py econ --symbols AAPL
```

### View Logs
```bash
# PostgreSQL logs
docker-compose logs -f postgres

# Redis logs
docker-compose logs -f redis

# LocalStack logs
docker-compose logs -f localstack

# All logs
docker-compose logs -f
```

## Development Workflow

### Typical Development Loop

```bash
# 1. Make code changes
#    Edit: loadpricedaily.py, data_source_router.py, etc.

# 2. Run locally to verify
export DB_HOST=localhost DB_USER=stocks DB_PASSWORD=''
python3 loadpricedaily.py --symbols AAPL,MSFT --parallelism 2

# 3. Check database results
psql -h localhost -U stocks -d stocks -c "
  SELECT * FROM price_daily WHERE symbol='AAPL' ORDER BY date DESC LIMIT 5;"

# 4. View watermark advancement
psql -h localhost -U stocks -d stocks -c "
  SELECT * FROM loader_watermarks WHERE loader='price_daily';"

# 5. Git commit and push
git add .
git commit -m "Feature: ..."
git push origin feature-branch
```

### Testing a New Loader

```bash
# 1. Create new loader (inherit from OptimalLoader)
#    File: load<name>.py

# 2. Test locally
export DB_HOST=localhost
python3 load<name>.py --symbols AAPL

# 3. Check watermarks
psql -h localhost -U stocks -d stocks -c "
  SELECT * FROM loader_watermarks WHERE loader='<table_name>';"

# 4. Verify data quality
psql -h localhost -U stocks -d stocks -c "
  SELECT COUNT(*), symbol FROM <table_name> GROUP BY symbol;"
```

## Performance Tips

### Increase Parallelism
```bash
# Default is 4, can go up to CPU cores
python3 loadpricedaily.py --parallelism 8
```

### Backfill Mode (Refetch Last N Days)
```bash
# Recalculate last 7 days
python3 loadpricedaily.py --backfill-days 7

# Useful after algorithm changes or fixes
```

### Check Bloom Filter Hit Rate
```bash
# In loader output, look for:
# rows_dedup_skipped=567  ← Bloom filter prevented these inserts
# rows_inserted=667       ← Actual new rows

# Hit rate = 567 / (567 + 667) = 45% skipped (good!)
```

### Monitor Database Load
```bash
# Via pgAdmin
http://localhost:5050 → Tools → Query Tool → pg_stat_activity

# Via psql
psql -h localhost -U stocks -d stocks -c "
  SELECT query, state, query_start FROM pg_stat_activity
  WHERE query NOT LIKE '%pg_stat%';"
```

## Debugging

### Loader Hangs or Crashes
```bash
# Check database connection
psql -h localhost -U stocks -d stocks -c "SELECT 1"

# Check Redis connection
redis-cli -h localhost ping

# Increase logging
export DEBUG=1
python3 loadpricedaily.py --symbols AAPL
```

### Memory/Disk Issues
```bash
# Check Docker resource usage
docker stats

# Check disk space
docker-compose exec postgres df -h

# Clean up old data
docker volume prune
docker image prune
```

### Database Locks
```bash
# Check locked tables
psql -h localhost -U stocks -d stocks -c "
  SELECT * FROM pg_locks
  WHERE NOT granted;"

# Kill long-running query
psql -h localhost -U stocks -d stocks -c "
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE duration > interval '5 minutes';"
```

## Environment Variables

Core variables (set before running loaders):

```bash
# Database
export DB_HOST=localhost           # Hostname or IP
export DB_PORT=5432               # PostgreSQL port
export DB_USER=stocks             # Username
export DB_PASSWORD=''             # (empty for local dev)
export DB_NAME=stocks             # Database name

# Redis (optional, for Bloom filter)
export REDIS_URL=redis://localhost:6379

# Alpaca API (if testing with real Alpaca)
export ALPACA_API_KEY=...         # From app.alpaca.markets
export ALPACA_API_SECRET=...
export ALPACA_API_BASE_URL=https://paper-api.alpaca.markets

# Logging
export LOG_LEVEL=INFO             # DEBUG, INFO, WARNING, ERROR
export DEBUG=1                    # Verbose output
```

## Production Parity

### What Matches Production
✓ PostgreSQL version (16)
✓ TimescaleDB → BRIN indexes (simulated via schema)
✓ Database schema (init_db.sql runs on startup)
✓ Watermark tracking
✓ Bloom filter dedup
✓ Data source routing (Alpaca → yfinance fallback)
✓ ECS task environment

### What's Different (Local Only)
✗ RDS endpoint (localhost instead of AWS)
✗ Secrets Manager (hardcoded values or LocalStack mock)
✗ EventBridge scheduling (run manually or use `docker exec`)
✗ Lambda (run via wrapper script, not actual Lambda runtime)

### To Test AWS Features Locally
```bash
# Start LocalStack with Lambda support
docker-compose --profile localstack up -d localstack

# Deploy to LocalStack
aws --endpoint-url http://localhost:4566 lambda create-function \
  --function-name loader-test \
  --zip-file fileb://lambda-loaders.zip \
  --handler lambda_loader_wrapper.handler \
  --runtime python3.11 \
  --region us-east-1

# Invoke
aws --endpoint-url http://localhost:4566 lambda invoke \
  --function-name loader-test \
  --payload '{"loader":"econ"}' \
  /tmp/output.json
```

## Cleanup

```bash
# Stop services (keep volumes)
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v

# Remove all Docker resources (containers, images, networks)
docker-compose down --rmi all
```

## References

- [docker-compose.yml](./docker-compose.yml) — Service definitions
- [init_db.sql](./init_db.sql) — Database schema
- [BRIN_DEPLOYMENT_GUIDE.md](./BRIN_DEPLOYMENT_GUIDE.md) — Database optimization
- [WATERMARK_INCREMENTAL_GUIDE.md](./WATERMARK_INCREMENTAL_GUIDE.md) — Watermark tracking
- [optimal_loader.py](./optimal_loader.py) — Base loader class
