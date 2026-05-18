# Complete Data Loading Guide - Local & AWS

**Goal**: Load all 10,142 symbols with complete price history, fundamentals, and reference data. No dropped symbols. Proof via CloudWatch logs.

## Quick Start

### Option A: Local Development (No AWS needed)

```bash
# 1. Set up database credentials
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=your_password

# 2. Initialize database
python3 init_database.py

# 3. Load stock symbols (Tier 0)
python3 loaders/loadstocksymbols.py

# 4. Load price data (Tier 1) - full load takes ~1 hour
python3 bulk_load_prices.py --full

# 5. Load reference data (Tier 2)
python3 run_full_load.py --tier 2

# 6. Validate everything loaded
python3 run_full_load.py --validate-only
```

### Option B: AWS RDS (Full production load)

Prerequisites:
- AWS credentials configured
- RDS PostgreSQL instance up
- Database credentials in AWS Secrets Manager

```bash
# 1. Set up credentials (read from Secrets Manager)
export DATABASE_SECRET_ARN=arn:aws:secretsmanager:us-east-1:xxx:secret:algo-db-xxx

# 2. Initialize database (if first time)
python3 init_database.py

# 3. Load all tiers
python3 run_full_load.py --tier 1  # Load prices
python3 run_full_load.py --tier 2  # Load reference data

# 4. Monitor in AWS:
# - CloudWatch Logs: /aws/ecs/algo-loaders/*
# - RDS Metrics: Check data loaded in database
# - Lambda: Check worker invocations and errors
```

## Detailed Steps

### Step 1: Prepare Database

```bash
# Local PostgreSQL
createdb algo_trading
psql algo_trading < schema.sql

# AWS RDS
# Use AWS Secrets Manager to store credentials
aws secretsmanager create-secret --name algo-db-prod \
  --secret-string '{"username":"postgres","password":"...","host":"xxx.rds.amazonaws.com","port":5432,"dbname":"algo_trading"}'
```

### Step 2: Load Stock Symbols (Tier 0)

This is REQUIRED - all other loaders depend on it.

```bash
python3 loaders/loadstocksymbols.py

# Validates:
# - ✓ Symbols table populated (10,142+ records)
# - ✓ Symbols are unique
# - ✓ Database connection works
```

### Step 3: Load Price Data (Tier 1)

Three approaches below, pick based on your needs:

#### Option 3A: Full Sequential Load (Local, ~1 hour)
```bash
python3 bulk_load_prices.py --full

# Validates:
# - All 10,142 symbols processed
# - Failure rate < 5%
# - No dropped symbols
# - ~50+ rows per symbol (5 years history)
```

#### Option 3B: Quick Sample Load (Testing, ~5 min)
```bash
python3 bulk_load_prices.py --limit 100

# Good for:
# - Testing setup
# - Verifying API connectivity
# - Quick validation
```

#### Option 3C: Parallel Load with Distributed Workers (AWS, ~15 min)
```bash
# Enqueue symbols to SQS
export LOADER_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/xxx/algo-loader-symbols
python3 loaders/load_prices_distributed.py --enqueue

# Lambda workers automatically pick up and load
# Monitor in CloudWatch: /aws/lambda/algo-price-loader
```

### Step 4: Load Reference Data (Tier 2)

Includes financials, earnings, economic data, sentiment, etc.

```bash
python3 run_full_load.py --tier 2

# This runs:
# - Company profiles
# - Annual financials (income, balance, cash flow)
# - Quarterly financials
# - Earnings history, estimates, revisions
# - Analyst sentiment and upgrades/downgrades
# - Economic data (FRED, AAII, Fear & Greed)
# - Market structure (sectors, industries, seasonality)
# - TTM (trailing 12-month) aggregates

# Typical duration: 30-45 minutes
```

### Step 5: Load Computed Metrics (Tier 3+)

Depends on price and reference data.

```bash
python3 run_full_load.py --tier 3

# This computes:
# - Growth metrics (growth rates, margins)
# - Quality metrics (ROE, debt ratios)
# - Value metrics (P/E, P/B, dividend yield)
# - Stock scores (composite ranking)
# - Technical signals (buy/sell indicators)
```

### Step 6: Validate and Report

```bash
# Generate validation report
python3 run_full_load.py --validate-only

# Expected output:
# ✓ Symbols: 10,142 records
# ✓ Daily prices: 500,000+ records
# ✓ Financials: 50,000+ records
# ✓ Earnings: 30,000+ records
# ✓ All data present, no gaps
```

## Troubleshooting

### Issue: "Database password not available"

**Solution**: Set credentials explicitly
```bash
# Option 1: Environment variable
export DB_PASSWORD=your_password
export DB_USER=postgres
export DB_HOST=localhost

# Option 2: AWS Secrets Manager (for production)
export DATABASE_SECRET_ARN=arn:aws:secretsmanager:us-east-1:xxx:secret:algo-db-xxx

# Option 3: Store in PowerShell profile (Windows)
[Environment]::SetEnvironmentVariable("DB_PASSWORD", "your_password", "User")
```

### Issue: "yfinance API error / Rate limited"

**Solution**: Wait and retry
```bash
# yfinance has built-in exponential backoff
# First failure: wait 1s, retry
# Second failure: wait 2s, retry
# Third failure: skip symbol, move to next

# Can also be network issue in AWS:
# - Check VPC egress rules (must allow HTTPS to yfinance)
# - Check NAT gateway route
# - Try from within EC2 instance directly
```

### Issue: "Alpaca auth failed (403)"

**Solution**: yfinance fallback activates
```bash
# If Alpaca fails, automatically falls back to yfinance
# No action needed - system handles it

# To debug:
grep "Alpaca" logs/* | grep 403
# If you see 403 errors, Alpaca API subscription might not include data API
```

### Issue: AWS Lambda workers not starting

**Solution**: Check SQS queue and Lambda config
```bash
# Verify queue has messages
aws sqs get-queue-attributes --queue-url $QUEUE_URL --attribute-names ApproximateNumberOfMessages

# Check Lambda concurrency
aws lambda get-function-concurrency --function-name algo-price-loader

# Check IAM permissions
aws iam list-role-policies --role-name algo-lambda-execution-role
```

## Monitoring

### Local Load
```bash
# Watch loader output
tail -f loader.log | grep -E "Fetched|Inserted|Error"

# Monitor database
psql algo_trading -c "SELECT COUNT(*) FROM price_daily; SELECT COUNT(*) FROM stocks;"
```

### AWS Load

**CloudWatch Logs**:
```bash
# Watch loader progress
aws logs tail /aws/ecs/algo-loaders/price-loader --follow

# Check errors
aws logs tail /aws/ecs/algo-loaders/price-loader --filter-pattern "ERROR"

# Count successful loads
aws logs filter-log-events --log-group /aws/ecs/algo-loaders/price-loader --filter-pattern "✓" --query 'events | length(@)'
```

**CloudWatch Metrics**:
- `LoadedSymbols` - count of symbols with data (target: 10,142)
- `DroppedSymbols` - count with no data (target: 0)
- `FailedAttempts` - retries (target: trending to zero)
- `APILatency` - response times

**RDS Monitoring**:
```bash
# Check data loaded
SELECT table_name, count(*) FROM information_schema.tables WHERE table_schema = 'public';

# Check per-symbol data
SELECT symbol, COUNT(*) FROM price_daily GROUP BY symbol HAVING COUNT(*) < 100;

# Identify missing symbols
SELECT s.symbol FROM stocks s LEFT JOIN price_daily p ON s.symbol = p.symbol WHERE p.symbol IS NULL LIMIT 10;
```

## Expected Results

After full load completes:

```
Tier 0: Stock symbols
  ✓ 10,142 symbols loaded

Tier 1: Price data
  ✓ Daily prices: ~50+ rows per symbol
  ✓ ~500,000 total price records
  ✓ Load time: 30-60 minutes (depending on parallelism)

Tier 2: Reference data
  ✓ 50,000+ financial records
  ✓ 30,000+ earnings records
  ✓ Sector and industry data
  ✓ Economic indicators
  ✓ Load time: 30-45 minutes

Tier 3+: Computed metrics
  ✓ Quality, growth, value scores
  ✓ Technical indicators and signals
  ✓ Load time: 15-30 minutes

Total load time: ~2.5-3 hours (sequential), or ~1 hour (AWS with parallelism)
Total data: ~1 million records across all tables
No errors: All symbols processed, no data dropped
```

## CloudWatch Log Proof

Final validation query:

```bash
# Count successful loads
aws logs filter-log-events \
  --log-group /aws/ecs/algo-loaders \
  --filter-pattern '[timestamp, level="INFO", message="✓" || message="Loaded"]' \
  --start-time $(($(date +%s)*1000 - 3600000)) \
  --query 'events | length(@)' | jq 'add'

# Expected: > 10,000 (one per symbol or batch)

# Check for errors
aws logs filter-log-events \
  --log-group /aws/ecs/algo-loaders \
  --filter-pattern '[level="ERROR"]' \
  --query 'events | length(@)' | jq 'add'

# Expected: 0 (or very close to 0 for transient errors)

# Get summary
aws logs describe-log-streams \
  --log-group /aws/ecs/algo-loaders \
  --query 'logStreams[*].[logStreamName,storedBytes,firstEventTimestamp,lastEventTimestamp]' \
  | jq 'map([.[0], (.[1]/1024/1024 | tostring + "MB"), ((.[3]-.[2])/1000/60 | tostring + " min")])'
```

## Success Criteria

✓ Task complete when:

1. **All symbols loaded**: 10,142 symbols in database with no gaps
2. **All data loaded**: Every tier (0-3) completes successfully
3. **No data loss**: No symbols dropped due to rate limits or errors
4. **CloudWatch proof**: Logs show clean completion, minimal errors
5. **Data validated**: Sample queries show expected data volume
6. **Both environments**: Data in local PostgreSQL AND AWS RDS (if applicable)

## Next Steps

1. Run `python3 bulk_load_prices.py --limit 100` to test locally
2. Verify database credentials work
3. Check for yfinance/Alpaca connectivity
4. Run full load `python3 bulk_load_prices.py --full`
5. Validate data in database
6. Repeat for AWS environment with CloudWatch monitoring
