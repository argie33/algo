# Step Functions EOD Pipeline Verification

## Goal
Verify that the Step Functions orchestration pipeline executed successfully and populated all required data tables.

## Step Functions Pipeline

**Name:** `algo-eod-orchestrator-dev`  
**Type:** AWS Step Functions State Machine  
**Trigger:** EventBridge scheduled rule or manual invocation  
**Duration:** ~20-30 minutes for full execution

## Pipeline Phases

The EOD pipeline executes in the following order:

### Phase 0: Pre-Flight Checks
- Verify database connectivity
- Check AWS service availability
- Validate environment configuration

### Phase 1: Stock Symbols (Tier 0)
- **Loader:** `loaders/load_symbols.py`
- **Data Source:** Alpaca API
- **Output Table:** `stock_symbols`
- **Expected Records:** 5,000-10,000 symbols

### Phase 2: Historical Prices (Tier 1)
- **Loader:** `loaders/load_price_daily.py`
- **Data Source:** Alpaca API historical data
- **Output Table:** `price_daily`
- **Expected Records:** 1,500,000+ daily price records
- **Typical Duration:** 10-15 minutes

### Phase 3: Market Data (Tier 2)
- **Loaders:** Multiple data sources
- **Output Tables:** `market_overview`, `sector_performance`, `economic_data`

### Phase 4: Technical Signals (Tier 3)
- **Loader:** `loaders/load_signals.py` (derived from price data)
- **Output Table:** `signals`
- **Computation:** Real-time signal calculation

### Phase 5: Trading Signals (Tier 4)
- **Loader:** `loaders/load_trade_signals.py`
- **Output Table:** `trade_signals`

### Phase 6-7: Reporting & Monitoring
- Data quality checks
- CloudWatch logs and metrics
- SNS alerts on failure

## Verification Checklist

### ✅ Database Tables Population

Check table row counts via AWS RDS:

```sql
SELECT 
  'stock_symbols' as table_name, 
  COUNT(*) as row_count 
FROM stock_symbols
UNION ALL
SELECT 'price_daily', COUNT(*) FROM price_daily
UNION ALL
SELECT 'signals', COUNT(*) FROM signals
UNION ALL
SELECT 'trade_signals', COUNT(*) FROM trade_signals;
```

**Expected Results:**
| Table | Min Rows | Max Rows |
|-------|----------|----------|
| stock_symbols | 5,000 | 50,000 |
| price_daily | 1,000,000 | 2,000,000 |
| signals | 10,000 | 100,000 |
| trade_signals | 1,000 | 10,000 |

### ✅ Step Functions Execution History

Check AWS Console → Step Functions → `algo-eod-orchestrator-dev`

Look for:
- [ ] Most recent execution completed successfully
- [ ] Execution timestamp (should be recent - within last 24 hours)
- [ ] All phases passed
- [ ] No failed state machines
- [ ] Execution duration logged (15-30 minutes typical)

### ✅ CloudWatch Logs

Check CloudWatch Logs Groups:
- `/aws/stepfunctions/algo-eod-orchestrator-dev`
- `/aws/ecs/algo-loaders-*`

Look for:
- [ ] Successful phase transitions
- [ ] No ERROR or FATAL level messages
- [ ] Loader completion messages
- [ ] Database insert counts

### ✅ EventBridge Rule Status

Check EventBridge Rules:
- **Rule Name:** `algo-eod-trigger` (typically)
- **Status:** ENABLED
- **Schedule:** Usually 4:05 PM ET (21:05 UTC)
- **Last Trigger:** Recent timestamp

### ✅ RDS Database Connectivity

Verify database is accessible:
```bash
# From Lambda or ECS task
psql -h <RDS_ENDPOINT> -U <DB_USER> -d stocks -c "SELECT NOW();"
```

Should return current timestamp if connection successful.

### ✅ API Health Check

Test API Lambda returns 200:
```bash
curl https://<API_GATEWAY_URL>/api/health
```

Expected response:
```json
{"status": "healthy", "database": "connected"}
```

## Troubleshooting

### Issue: Step Functions Never Executed

**Possible Causes:**
1. EventBridge rule disabled
2. Step Functions state machine not created
3. IAM role missing permissions
4. Lambda execution blocked by VPC

**Fix:**
- Check EventBridge rule is ENABLED
- Verify Step Functions state machine exists and has correct IAM role
- Check VPC security groups allow egress to RDS

### Issue: Step Functions Failed Mid-Phase

**Possible Causes:**
1. Database credentials invalid
2. Loader crashed or timed out
3. Data source API unavailable
4. RDS storage full

**Check:**
- CloudWatch logs for specific error message
- RDS free storage space
- Alpaca API status
- Database user permissions

### Issue: Data Tables Empty

**Possible Causes:**
1. Loaders run but insert 0 rows
2. Data source returned empty results
3. Database transaction rolled back on error
4. Wrong database specified

**Check:**
- CloudWatch logs for loader output
- Database credentials in Secrets Manager
- RDS database name matches loader configuration
- API rate limits not exceeded

## Manual Execution

To trigger the pipeline manually:

```bash
# Start Step Functions execution
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:<ACCOUNT>:stateMachine:algo-eod-orchestrator-dev \
  --region us-east-1
```

Monitor execution in AWS Console.

## Success Criteria

✅ **Pipeline Successful When:**
1. Step Functions execution shows all phases completed
2. `stock_symbols` table has 5,000+ rows
3. `price_daily` table has 1,000,000+ rows
4. API health endpoint returns 200
5. CloudWatch logs show no errors
6. RDS CPU and connections normal

---

**Last Updated:** 2026-05-18  
**Next Steps:** 
1. Verify AWS credentials to check Step Functions
2. Review database row counts
3. Check CloudWatch logs for any errors
4. Confirm API is responding to requests
