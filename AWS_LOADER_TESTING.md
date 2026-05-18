# AWS Loader Testing & Verification

## Quick Verify: Check Loaders Can Run

Test the Alpaca credentials fix:

```bash
# Check if loaders are scheduled
aws events list-rules --name-prefix algo-stock --region us-east-1

# View next scheduled run times
aws events describe-rule --name algo-stock_symbols-schedule --region us-east-1
```

## View CloudWatch Logs

Check real-time loader execution in CloudWatch:

```bash
# Watch stock prices loader (runs ~4am ET daily)
aws logs tail /ecs/algo-stock_prices_daily-loader --follow --region us-east-1

# Watch signals loader (runs ~5pm ET daily)  
aws logs tail /ecs/algo-signals_daily-loader --follow --region us-east-1

# Watch orchestrator (runs ~5:30pm ET daily)
aws logs tail /ecs/algo-algo_orchestrator-loader --follow --region us-east-1
```

## Friday Data Status

Today is **May 17, 2026 (Friday)**:
- **Before 4pm ET:** Loaders fetch partial Friday data (intraday)
- **After 4pm ET:** Loaders fetch full Friday close prices
- **Data source:** Alpaca API (live prices, not cached)

Loaders automatically pull `date.today()` without modification.

## Verify Database Received Data

Connect to RDS and confirm data was loaded:

```bash
psql -U stocks -d stocks -h $DB_HOST -W

# Inside psql:
SELECT COUNT(*) FROM stock_symbols;
SELECT symbol, MAX(date) FROM price_daily GROUP BY 1 LIMIT 5;
SELECT COUNT(*) FROM buy_sell_signal_daily WHERE date = CURRENT_DATE;
```

## Troubleshooting Loader Failures

### Check ECS Task Status

```bash
# List recent tasks
aws ecs list-tasks --cluster algo-cluster --region us-east-1

# Get task details and errors
aws ecs describe-tasks --cluster algo-cluster --tasks <task-arn> --region us-east-1
```

### View Full Error Logs

```bash
# Get all logs from a log group
aws logs describe-log-streams --log-group-name /ecs/algo-stock_prices_daily-loader

# Tail specific stream
aws logs tail /ecs/algo-stock_prices_daily-loader/ecs/algo-stock_prices_daily --follow
```

## Key Fixes Applied

✅ **Alpaca credentials now injected:** APCA_API_KEY_ID and APCA_API_SECRET_KEY added to all loader task definitions

✅ **Secrets Manager integration:** Credentials retrieved from algo-algo-secrets-dev at runtime

✅ **Database connection:** RDS proxy handles connection pooling for 40+ concurrent loaders

## Expected Schedule (Mon-Fri)

- **3:30am ET** - Stock symbols, market data batch
- **4:00am ET** - Price loaders (daily, weekly, monthly for stocks + ETFs)
- **5:00pm ET** - Trading signal generation (runs via Step Functions)
- **5:30pm ET** - Orchestrator execution (paper trading, risk analysis)

All times are US Eastern Time.
