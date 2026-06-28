# Critical Data Loaders Deployment Guide

## Problem Summary

The market exposure calculation engine requires two critical data tables that were missing from the infrastructure:

1. **ad_line_daily** - Advance/Decline line direction (6 points in market exposure score)
2. **credit_spreads** - High-Yield OAS spreads (10 points in market exposure score)

Without these tables, market exposure calculations fail with:
```
ERROR: relation "ad_line_daily" does not exist
ERROR: relation "credit_spreads" does not exist
```

## Solution Components

### 1. Database Migrations

Two new migrations have been created:

- **migrations/versions/099_create_ad_line_daily_table.sql** - Creates ad_line_daily table
- **migrations/versions/100_create_credit_spreads_table.sql** - Creates credit_spreads table

These migrations define the required schema with proper indexing for fast lookups.

### 2. Data Loaders

Two new loader modules have been created:

- **loaders/load_ad_line_daily.py** - Computes advance/decline line from trend_template_data
- **loaders/load_credit_spreads.py** - Fetches HY OAS from FRED API

## Deployment Instructions

### Step 1: Apply Database Migrations

Run the migration runner in your AWS Lambda environment or local development environment:

```bash
# Apply all pending migrations
python3 migrations/run.py apply --all

# Or apply specific migrations
python3 migrations/run.py apply 099_create_ad_line_daily_table
python3 migrations/run.py apply 100_create_credit_spreads_table

# Check migration status
python3 migrations/run.py status
```

**Required environment variables for local migrations:**
```bash
export DB_HOST="your-rds-endpoint.us-east-1.rds.amazonaws.com"
export DB_PORT="5432"
export DB_NAME="algo"
export DB_USER="postgres"
export DB_PASSWORD="your-password"
```

### Step 2: Configure Environment Variables

For the credit spreads loader to work, you need a FRED API key:

```bash
# Get free API key from: https://fred.stlouisfed.org/docs/api/
export FRED_API_KEY="your-fred-api-key"
```

Store this in AWS Secrets Manager:
```bash
aws secretsmanager create-secret \
    --name algo/fred-api-key \
    --secret-string '{"api_key":"your-key"}'
```

### Step 3: Create ECS Task Definitions

Add task definitions for the new loaders. These follow the standard pattern:

**Template for ad_line_daily loader:**
```json
{
  "family": "algo-load_ad_line_daily-loader",
  "containerDefinitions": [{
    "name": "loader",
    "image": "your-account.dkr.ecr.us-east-1.amazonaws.com/algo:latest",
    "command": ["python3", "loaders/load_ad_line_daily.py"],
    "environment": [
      {"name": "DB_ENDPOINT", "value": "your-rds-endpoint"},
      {"name": "DB_NAME", "value": "algo"}
    ]
  }]
}
```

**Template for credit_spreads loader:**
```json
{
  "family": "algo-load_credit_spreads-loader",
  "containerDefinitions": [{
    "name": "loader",
    "image": "your-account.dkr.ecr.us-east-1.amazonaws.com/algo:latest",
    "command": ["python3", "loaders/load_credit_spreads.py"],
    "environment": [
      {"name": "DB_ENDPOINT", "value": "your-rds-endpoint"},
      {"name": "DB_NAME", "value": "algo"},
      {"name": "FRED_API_KEY", "value": "your-fred-key"}
    ]
  }]
}
```

### Step 4: Initial Data Load

Trigger the loaders to populate historical data:

**Option A: Via Lambda trigger endpoint**
```bash
# Trigger ad_line_daily loader
curl -X POST https://your-api.execute-api.us-east-1.amazonaws.com/api/algo/trigger-loader \
  -H "Authorization: Bearer your-token" \
  -d '{"loader_name":"load_ad_line_daily"}'

# Trigger credit_spreads loader
curl -X POST https://your-api.execute-api.us-east-1.amazonaws.com/api/algo/trigger-loader \
  -H "Authorization: Bearer your-token" \
  -d '{"loader_name":"load_credit_spreads"}'
```

**Option B: Local testing**
```bash
cd algo
# Test ad_line_daily loader (requires trend_template_data to be populated)
python3 loaders/load_ad_line_daily.py --backfill-days 90

# Test credit_spreads loader (requires FRED_API_KEY)
export FRED_API_KEY="your-key"
python3 loaders/load_credit_spreads.py --backfill-days 90
```

### Step 5: Schedule Daily Updates

Configure EventBridge rules to run the loaders daily after market close:

```bash
# ad_line_daily loader - run daily at 5 PM ET
aws events put-rule \
  --name algo-ad-line-daily-schedule \
  --schedule-expression "cron(0 21 * * ? *)" \
  --state ENABLED

# credit_spreads loader - run daily at 5 PM ET
aws events put-rule \
  --name algo-credit-spreads-daily-schedule \
  --schedule-expression "cron(0 21 * * ? *)" \
  --state ENABLED
```

## Data Source Details

### Advance-Decline Line (ad_line_daily)

- **Source**: Computed from trend_template_data (existing table)
- **Computation**: Counts stocks with price > 50-day SMA vs those below
- **Direction**: "up" if advances > declines, "down" otherwise
- **Update frequency**: Daily after market close
- **Data dependency**: Requires trend_template_data with signal scores

### High-Yield OAS (credit_spreads)

- **Source**: FRED API (Federal Reserve Economic Data)
- **Series ID**: BAMLH0A0HYM2 (Bank of America Merrill Lynch High Yield OAS)
- **Data frequency**: Daily (though FRED updates may lag 1-2 days)
- **Update frequency**: Daily after market close
- **External dependency**: Requires FRED API key (free registration at fred.stlouisfed.org)

## Monitoring and Verification

### Verify data is being loaded

```sql
-- Check ad_line_daily
SELECT COUNT(*), MAX(date), MIN(date) FROM ad_line_daily;
SELECT * FROM ad_line_daily WHERE date >= CURRENT_DATE - INTERVAL '7 days' ORDER BY date DESC;

-- Check credit_spreads
SELECT COUNT(*), MAX(date), MIN(date) FROM credit_spreads;
SELECT * FROM credit_spreads WHERE date >= CURRENT_DATE - INTERVAL '7 days' ORDER BY date DESC;
```

### Watch loader logs

```bash
# Check ECS task execution
aws ecs describe-tasks \
  --cluster algo-cluster \
  --tasks $(aws ecs list-tasks --cluster algo-cluster --family-prefix load_ad_line_daily | jq -r '.taskArns[0]') \
  --query 'tasks[0].stopCode'

# View CloudWatch logs
aws logs tail /ecs/algo-load_ad_line_daily-loader --follow
aws logs tail /ecs/algo-load_credit_spreads-loader --follow
```

### Alert on missing data

The market exposure engine will fail loudly if these tables are empty:
- Check database health monitoring dashboard for "AD_LINE CRITICAL" or "CREDIT_SPREAD CRITICAL" errors
- Configure CloudWatch alarms for loader task failures
- Set up notifications when market_exposure_daily table stops receiving updates

## Dependencies

### ad_line_daily loader requires:
- trend_template_data table (must be populated by signal_quality_scores loader)
- Database write access

### credit_spreads loader requires:
- FRED API key (free registration)
- Database write access
- Internet connectivity to api.stlouisfed.org
- RequestsHTTP library (already in requirements.txt)

## Troubleshooting

### "No advance-decline data available for [date range]"
**Cause**: trend_template_data is empty
**Solution**: Ensure signal_quality_scores loader has run successfully

### "FRED API request failed"
**Cause**: API key not set, network unreachable, or FRED service unavailable
**Solution**: 
1. Verify FRED_API_KEY environment variable is set
2. Test API key: `curl "https://api.stlouisfed.org/fred/series/data?series_id=BAMLH0A0HYM2&api_key=YOUR_KEY&file_type=json"`
3. Check network connectivity to FRED endpoint

### Market exposure still fails with "relation does not exist"
**Cause**: Migrations weren't applied
**Solution**: 
1. Run `python3 migrations/run.py status` to check applied migrations
2. Apply missing migrations with `python3 migrations/run.py apply --all`
3. Verify tables exist: `\dt ad_line_daily credit_spreads` in psql

## Performance Notes

- **ad_line_daily**: Fast computation from existing data (~1 second for full backfill)
- **credit_spreads**: Slower due to FRED API calls (~5-10 seconds per 1000 dates)
- Both loaders run in global mode (no per-symbol parallelism needed)
- Recommended run time: After market close (5 PM ET) when all data is fresh

## Next Steps

1. **Immediate**: Apply migrations to RDS database
2. **Today**: Configure FRED API key in Secrets Manager
3. **This week**: Create ECS task definitions and schedule EventBridge rules
4. **Verify**: Manually trigger loaders and confirm data arrives
5. **Monitor**: Watch loader logs and market_exposure_daily updates for 3-5 days

## References

- FRED API Documentation: https://fred.stlouisfed.org/docs/api/
- HY OAS Series: https://fred.stlouisfed.org/series/BAMLH0A0HYM2
- Market Exposure Engine: algo/risk/market_exposure.py
- Database Health Monitor: algo/orchestration/database_health_monitor.py
