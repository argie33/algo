# AWS Loaders - Local Testing & Deployment

You have 59 AWS-integrated loaders that fetch and populate your database. This guide shows how to run them locally to test before pushing to AWS.

## 🚀 Quick Start

### 1. Verify Environment Setup
```bash
# Check database is running
pg_isready -h localhost -p 5432

# Check .env.local has database credentials
cat .env.local | grep DB_
```

### 2. Initialize Schema (First Time Only)
```bash
python3 init_database.py
```
This creates all tables the loaders expect. Safe to run multiple times.

### 3. Run the Loader Orchestrator
```bash
# Run essential loaders (symbols + prices + company data)
python3 run-loaders.py

# Run only critical loaders (symbols + prices)
python3 run-loaders.py --critical-only

# Reset progress and start over
python3 run-loaders.py --reset-progress

# Run specific loader only
python3 run-loaders.py --loader loadstocksymbols.py
```

## 📊 What Gets Loaded (In Order)

### Phase 1: Foundation (CRITICAL)
- **loadstocksymbols.py** - NASDAQ/NYSE symbol list (required by everything else)

### Phase 2: Price Data (CRITICAL)
- **loadpricedaily.py** - Daily OHLCV data (required by signals, technicals)

### Phase 3: Company Data
- **loaddailycompanydata.py** - Company info, positioning, analyst estimates
  - Includes: sector, industry, business summary, insider transactions, positioning

### Phase 4: Financial Statements
- **loadannualincomestatement.py** - Revenue, net income, margins
- **loadannualbalancesheet.py** - Assets, liabilities, equity
- **loadannualcashflow.py** - Operating, investing, financing cash flows

### Phase 5: Technical & Sentiment
- **loadtechnicalindicators.py** - Moving averages, RSI, MACD, Bollinger Bands
- **loadsentiment.py** - Market sentiment scores

### Phase 6: Trading Signals
- **loadbuyselldaily.py** - Daily buy/sell signals based on technicals
- **loadstockscores.py** - Composite scores (depends on all above)

## ⏱️ Execution Timeline

| Phase | Loader | Time | Notes |
|-------|--------|------|-------|
| 1 | loadstocksymbols.py | 2-5 min | API call per symbol, ~7500 symbols |
| 2 | loadpricedaily.py | 30-60 min | Fetches 365 days price history |
| 3 | loaddailycompanydata.py | 20-40 min | Company info + positioning |
| 4a | loadannualincomestatement.py | 10-20 min | Financial statements |
| 4b | loadannualbalancesheet.py | 10-20 min | Balance sheet data |
| 4c | loadannualcashflow.py | 10-20 min | Cash flow data |
| 5a | loadtechnicalindicators.py | 20-30 min | Requires price data |
| 5b | loadsentiment.py | 5-10 min | Market sentiment |
| 6a | loadbuyselldaily.py | 20-30 min | Signals from prices + technicals |
| 6b | loadstockscores.py | 10-20 min | Requires all other data |
| **TOTAL** | **All** | **2-4 hours** | With rate limiting, no API bans |

## 🔧 Key Features of run-loaders.py

✅ **Progress Tracking** - Saves which loaders completed, resumes on restart
✅ **Dependency Order** - Runs loaders in the correct sequence
✅ **Error Handling** - Critical loaders abort if they fail; non-critical continue
✅ **Rate Limiting** - 2-second delay between loaders (configurable)
✅ **Database Check** - Verifies connection before starting
✅ **Schema Init** - Automatically initializes schema (optional with --skip-schema)
✅ **Summary Report** - Shows counts of loaded records

## 🎯 Workflows

### Development Testing
```bash
# Test schema initialization
python3 init_database.py

# Load just symbols and prices (quick test)
python3 run-loaders.py --critical-only

# Check what loaded
psql -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily;"
```

### Full Data Load (Local)
```bash
# One command - loads everything
python3 run-loaders.py

# Watch progress
tail -f .loader-progress.json
```

### Resume Interrupted Load
```bash
# Loaders track progress automatically
# If interrupted (Ctrl+C), just run again
python3 run-loaders.py

# Continue from last failure
# (Critical loaders abort on failure, non-critical skip)
```

### Reset and Start Over
```bash
python3 run-loaders.py --reset-progress
```

## 🔍 Monitoring & Verification

### Check Progress
```bash
# View progress file
cat .loader-progress.json

# Sample output:
# {
#   "completed": ["loadstocksymbols.py", "loadpricedaily.py"],
#   "failed": []
# }
```

### Verify Data Loaded
```bash
# Connect to database
psql -U stocks -d stocks

# Check record counts
SELECT 'symbols' as table_name, COUNT(*) FROM stock_symbols
UNION ALL
SELECT 'prices', COUNT(*) FROM price_daily
UNION ALL
SELECT 'company data', COUNT(*) FROM company_profile
UNION ALL
SELECT 'technical', COUNT(*) FROM technical_indicators;

# Check last update
SELECT symbol, MAX(fetched_at) FROM price_daily GROUP BY symbol ORDER BY MAX(fetched_at) DESC LIMIT 5;
```

### Monitor Live Execution
```bash
# In another terminal, watch logs
tail -f /tmp/loader.log

# Check database activity
psql -U stocks -d stocks -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"
```

## ⚠️ Common Issues & Solutions

### "Cannot connect to database"
```bash
# Start PostgreSQL
postgres -D /var/lib/postgresql/data

# Or on Mac with Homebrew
brew services start postgresql@15
```

### "Loader hangs / takes too long"
- Check network connectivity: `ping yahoo.com`
- Check for timeouts in loader logs
- Increase timeout in run-loaders.py if needed

### "Symbol table empty after loadstocksymbols.py"
- Network error fetching symbol list from NASDAQ
- Check: `grep -i error .loader-progress.json`
- Re-run: `python3 run-loaders.py --loader loadstocksymbols.py`

### "Rate limited / 429 errors"
- Loaders implement built-in rate limiting
- If still hitting limits, increase RATE_LIMIT_SECONDS in run-loaders.py
- Yfinance is free but has soft limits (~100 req/min)

### "Some loaders fail but others complete"
- Non-critical loaders skip on failure, continue loading
- Critical loaders (symbols, prices) abort to prevent corruption
- Check `.loader-progress.json` to see what failed
- Fix and re-run with same command

## 📋 Loader Dependencies

```
loadstocksymbols.py
    ↓
loadpricedaily.py ────→ loadtechnicalindicators.py ─┐
    ↓                                                 ├→ loadbuyselldaily.py
loaddailycompanydata.py                             ├→ loadstockscores.py
    ↓
loadannualincomestatement.py
loadannualbalancesheet.py
loadannualcashflow.py
```

## 🚀 Pushing to AWS

Once local testing is complete:

1. **Verify all data loaded correctly**
   ```bash
   python3 run-loaders.py
   # Check summary output for record counts
   ```

2. **Run against AWS database**
   ```bash
   # Set AWS database credentials in .env.aws
   export DB_HOST=<aws-rds-endpoint>
   export DB_USER=<aws-user>
   export DB_PASSWORD=<aws-password>
   export DB_NAME=stocks
   
   python3 run-loaders.py --skip-schema  # Schema should exist on AWS
   ```

3. **Monitor AWS ECS task** (if using Lambda/ECS)
   - CloudWatch logs: `/aws/ecs/stocks-loader`
   - Check for failures: `ERROR` in logs

4. **Verify AWS data**
   ```bash
   psql -h <aws-endpoint> -U stocks -d stocks
   SELECT COUNT(*) FROM price_daily;
   ```

## 📖 Individual Loader Documentation

Each loader is standalone and can run independently:

```bash
# Run a specific loader directly
python3 loadstocksymbols.py

# Loaders respect .env.local for database config
# and implement their own error handling
```

## 🔗 AWS Integration

These loaders are production-ready for AWS:

- **S3 Integration** - Some loaders upload processed data to S3
- **CloudWatch Logs** - All errors logged to CloudWatch
- **RDS Connection** - Uses VPC security groups for RDS access
- **Lambda Friendly** - Can be triggered from AWS Lambda
- **ECS Compatible** - Run as Docker containers on ECS
- **SNS Alerts** - Some loaders send success/failure to SNS

Run locally to test, push same code to AWS.

## Summary

```bash
# One-time setup
python3 init_database.py

# Load all data locally
python3 run-loaders.py

# Verify
psql -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols;"

# Ready for AWS!
```
