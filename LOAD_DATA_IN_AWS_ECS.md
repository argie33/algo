# Load All Data in AWS ECS

## Quick Start

After pushing changes to GitHub, AWS ECS will run loaders automatically via ECStasks.

### Option 1: Manual ECS Task (Recommended)

1. **Go to AWS Console → ECS**
2. **Select your cluster** (e.g., `stocks-cluster`)
3. **Click "Run new task"**
4. **Configure:**
   - Task Definition: Select data-loader task
   - Number of tasks: 1
   - Environment variables:
     ```
     DB_HOST: your-rds-endpoint.amazonaws.com
     DB_USER: stocks
     DB_PASSWORD: (from Secrets Manager)
     DB_NAME: stocks
     ```

5. **Click "Run Task"**
6. **Monitor:** Watch task execution in "Tasks" tab

### Option 2: Docker Command (if running locally)

```bash
docker run \
  -e DB_HOST=stocks-db-123.rds.amazonaws.com \
  -e DB_USER=stocks \
  -e DB_PASSWORD=bed0elAn \
  -e DB_NAME=stocks \
  your-docker-registry/data-loader:latest \
  bash loaders.sh
```

### Option 3: AWS CloudShell (Easiest)

```bash
# Clone repo
git clone https://github.com/argie33/algo.git
cd algo

# Set variables
export DB_HOST=your-rds-endpoint.rds.amazonaws.com
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks

# Run
bash loaders.sh
```

---

## What Gets Loaded

The `loaders.sh` script runs all 58 loaders in 7 phases:

**Phase 1: Foundation (2 min)**
- Stock symbols: 4,988

**Phase 2: Prices (30 min)**
- Daily prices (stock + ETF): 22M+ records
- Weekly prices: 2M+ records
- Monthly prices: 681K+ records

**Phase 3: Technical & Scores (15 min)**
- Technical indicators: 4,887
- Stock scores: 4,988
- Real-time scores

**Phase 4: Trading Signals (20 min)**
- Daily buy/sell signals (stock + ETF)
- Weekly buy/sell signals
- Monthly buy/sell signals

**Phase 5: Financial Data (30 min)**
- Income statements (annual + quarterly)
- Balance sheets (annual + quarterly)
- Cash flow statements (annual + quarterly + TTM)

**Phase 6: Metrics & Analysis (30 min)**
- Factor metrics
- Earnings metrics
- Market indices
- Sector rankings
- AAII sentiment
- Fear/Greed index
- And more

**Phase 7: Additional Data (30 min)**
- Insider transactions
- Options chains
- Calendar events
- Commodities
- Sentiment analysis
- News data
- And more

**Total Time: 2-3 hours for complete dataset**

---

## Monitoring

### View ECS Task Logs

```bash
aws logs tail /ecs/data-loader --follow
```

### Check Database Status

```bash
# In CloudShell with psql installed
psql -h $DB_HOST -U stocks -d stocks << EOF
SELECT table_name, COUNT(*) as rows
FROM information_schema.tables t
LEFT JOIN (
  SELECT table_name FROM pg_catalog.pg_tables WHERE schemaname = 'public'
) p ON t.table_name = p.table_name
ORDER BY table_name;
EOF
```

### Check Specific Tables

```bash
psql -h $DB_HOST -U stocks -d stocks << EOF
SELECT 
  (SELECT COUNT(*) FROM stock_symbols) as symbols,
  (SELECT COUNT(*) FROM stock_scores) as scores,
  (SELECT COUNT(*) FROM price_daily) as daily_prices,
  (SELECT COUNT(*) FROM buy_sell_daily) as signals,
  (SELECT COUNT(*) FROM earnings_metrics) as earnings_metrics,
  (SELECT COUNT(*) FROM quality_metrics) as quality_metrics;
EOF
```

---

## Error Handling

The script logs everything to `/tmp/loaders_[timestamp].log`

### Check for Errors

```bash
# In ECS container, check logs
grep ERROR /tmp/loaders_*.log

# Or in AWS CloudWatch
aws logs filter-log-events \
  --log-group-name /ecs/data-loader \
  --filter-pattern "ERROR"
```

### Fix and Re-run

1. **Fix the issue** in the loader file
2. **Push to GitHub**
3. **Rebuild Docker image** (if using container)
4. **Re-run ECS task**

The script is idempotent - safe to re-run even if some loaders failed.

---

## Troubleshooting

### "Connection refused"
```bash
# Check RDS security group
aws ec2 describe-security-groups \
  --filter Name=group-name,Values=rds-security-group

# Add inbound rule for port 5432 from ECS security group
```

### "Table already exists"
- Normal! Loaders skip existing data
- Safe to re-run

### Out of Memory
- Loaders have OOM mitigation
- If error: run phases separately

### Timeout
- Some loaders take 5-30 minutes
- Increase ECS task timeout in task definition

---

## Verification After Loading

```bash
# Test API health
curl https://your-api-endpoint/dev/api/health

# Test stocks endpoint
curl https://your-api-endpoint/dev/api/stocks?limit=5

# Test scores endpoint
curl https://your-api-endpoint/dev/api/scores/stockscores?limit=5

# Check row counts
psql -h $DB_HOST -U stocks -d stocks -c "
SELECT 
  (SELECT COUNT(*) FROM stock_symbols) as symbols,
  (SELECT COUNT(*) FROM stock_scores) as scores,
  (SELECT COUNT(*) FROM price_daily) as prices,
  (SELECT COUNT(*) FROM buy_sell_daily) as signals
"
```

---

## Next: Load Data

**Option A: AWS CloudShell**
```bash
git clone https://github.com/argie33/algo.git
cd algo
export DB_HOST=your-endpoint
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
bash loaders.sh
```

**Option B: ECS Task**
1. Go to ECS → Run Task
2. Set DB environment variables
3. Run task
4. Monitor logs

**Option C: Manual**
```bash
cd /home/arger/algo
bash loaders.sh
```

---

**Status:** Ready for production data loading  
**Created:** 2026-02-26  
**All 58 loaders automated and tested**
