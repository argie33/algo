# AWS Data Loading Guide

## Overview
This guide explains how to load all 58 data loaders into AWS RDS after code deployment.

## Prerequisites
- GitHub code pushed ✅
- Lambda deployed via GitHub Actions ✅
- RDS database running in AWS ✅
- Database credentials in Secrets Manager ✅

## Data Loading Status

### Already Loaded Locally ✅
- Stock Symbols: 4,988
- Daily Prices: 22,451,321
- Weekly Prices: 1,987,220
- Monthly Prices: 681,235
- Technical Indicators: 4,887
- Buy/Sell Signals: 56,644

### To Load in AWS
All remaining data can be loaded via CloudShell or EC2

## Option 1: AWS CloudShell (Easiest)

```bash
# 1. Open AWS CloudShell
#    AWS Console → CloudShell (top right)

# 2. Clone repository
git clone https://github.com/argie33/algo.git
cd algo

# 3. Set database credentials (from Secrets Manager)
export DB_HOST=your-rds-endpoint.rds.amazonaws.com
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=your_password
export DB_NAME=stocks

# 4. Load critical data
bash /tmp/load_all_data.sh

# 5. Monitor progress
tail -f /tmp/data_loading.log
```

## Option 2: Using Lambda Function

Create a Lambda layer with Python loaders and execute via API Gateway.

## Option 3: EC2 Instance

1. Launch EC2 instance (t2.micro)
2. Install Python 3.12
3. Run loaders directly

## Data Loader Order (Optimized)

### Phase 1: Foundation (2 min)
```bash
python3 loadstocksymbols.py
```

### Phase 2: Prices (20 min) - PARALLEL
```bash
python3 loadpricedaily.py &
python3 loadpriceweekly.py &
python3 loadpricemonthly.py &
wait
```

### Phase 3: Technical & Scores (10 min)
```bash
python3 loadtechnicalindicators.py
python3 loadstockscores.py
```

### Phase 4: Signals & Fundamentals (30 min)
```bash
python3 loadbuyselldaily.py &
python3 loadbuysellweekly.py &
python3 loadbuysellmonthly.py &
python3 loadfactormetrics.py &
python3 loadearningsmetrics.py &
python3 loadannualincomestatement.py &
python3 loadquarterlyincomestatement.py &
wait
```

## Verification

```bash
# Test Lambda health endpoint
curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/health

# Check database row counts
psql -h $DB_HOST -U stocks -d stocks -c "
  SELECT 
    (SELECT COUNT(*) FROM stock_symbols) as symbols,
    (SELECT COUNT(*) FROM price_daily) as daily_prices,
    (SELECT COUNT(*) FROM stock_scores) as scores,
    (SELECT COUNT(*) FROM buy_sell_daily) as signals
"
```

## Estimated Timeline

- CloudShell setup: 2 min
- Data loading: 60-90 min
- API verification: 5 min
- **Total: ~100 minutes**

## Troubleshooting

### Connection refused
```bash
# Verify RDS endpoint
aws rds describe-db-instances --query 'DBInstances[0].Endpoint'

# Check security group
aws ec2 describe-security-groups --filter Name=group-name,Values=rds-security-group
```

### Out of memory
- Loaders have OOM mitigation built-in
- Reduce worker count if needed
- Split loading into multiple sessions

### Duplicate key errors
- Normal on re-run (data already exists)
- Loaders are idempotent

## Success Indicators

- ✅ Health endpoint returns "healthy": true
- ✅ /api/stocks returns all 4,988+ symbols
- ✅ /api/scores/stockscores returns scores
- ✅ /api/price endpoints return historical data
- ✅ Database row counts match expected values

## Next Steps

1. Load all data via CloudShell
2. Run API tests
3. Monitor Lambda logs
4. Access frontend at CloudFront URL

## Support

- GitHub Actions logs: https://github.com/argie33/algo/actions
- AWS CloudWatch: Lambda logs for errors
- RDS metrics: Database performance monitoring

---
**Created:** 2026-02-26
**Status:** Ready for production data loading
