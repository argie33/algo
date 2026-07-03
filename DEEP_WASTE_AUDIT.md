# 🔴 DEEP WASTE AUDIT - THE REAL MONEY DRAIN
**Status:** Comprehensive investigation starting  
**Date:** 2026-07-03

---

## SURFACE-LEVEL WASTE (Already Fixed)
- ✅ RDS Proxy: $150/month (DONE)
- ✅ VPC Endpoints: $43/month (DONE)
- ✅ Performance Insights: $6/month (DONE)
- ✅ Lambda timeout: 300s (prevents masking)
- ⏳ Extra database: stocks_test (~$3/month)

**Subtotal Fixed: $202/month**

---

## DEEP WASTE - The Real Money Drain

### 1. **RDS STORAGE BLOAT** (Potentially $50-200/month)
**Status:** CRITICAL - Not yet investigated

RDS bill includes storage. We have:
- 61 GB allocated initially
- 100 GB maximum autoscale
- But we're probably not cleaning up old data

**Questions:**
- How much actual data is stored?
- Are there old test tables we can delete?
- Are there duplicate records we're not cleaning?
- Are logs/metrics tables growing unbounded?

**To Check:**
```sql
-- Table sizes (find the bloated ones)
SELECT schemaname, tablename, 
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size 
FROM pg_tables 
WHERE schemaname NOT IN ('information_schema','pg_catalog') 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Index sizes (unused indexes waste space)
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;

-- Check for orphaned data
SELECT * FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;  -- Dead tuples = space waste
```

**Potential Fix:**
- VACUUM ANALYZE all tables (reclaim unused space)
- DELETE old test/debug data
- Drop unused indexes
- Cleanup dead rows

**Estimated Savings:** $20-50/month if bloated

---

### 2. **INEFFICIENT QUERIES / SLOW LOADERS** (Wasting $30-100+/month)

**The Problem:**
Slow loaders = long-running ECS tasks = compute hours wasted

From memory audit:
- SEC EDGAR loaders taking too long
- yfinance snapshot with 5000+ symbol batches
- Metric loaders with insufficient parallelism

**To Check:**
```bash
# Look at actual ECS task run times
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name TaskRunTime \
  --dimensions Name=ServiceName,Value=algo \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Maximum,Average

# Check CloudWatch logs for SLOW loader runs
# Look for runs that take 30+ minutes
```

**Potential Fixes:**
- Increase parallelism (currently at 3-4, could be 5-8)
- Batch sizes optimization
- Query optimization in SEC EDGAR loaders
- Connection pooling issues

**Estimated Savings:** $30-100/month if optimized

---

### 3. **LOGGING & CLOUDWATCH STORAGE** (Potentially $20-50+/month)

**The Problem:**
- CloudWatch logs retention is 3 days = but we have 28+ loaders
- Each loader generates logs
- Older logs archived to S3 (also costs storage)

**To Check:**
```bash
# Check CloudWatch log group sizes
aws logs describe-log-groups --region us-east-1 \
  --query 'logGroups[].{name:logGroupName, size:storedBytes}' \
  --output table | sort by storedBytes

# See what's taking up space
aws logs list-log-streams --log-group-name /ecs/algo-cluster \
  --order-by LastEventTime --descending --max-items 100
```

**Potential Fixes:**
- Reduce log verbosity (less DEBUG logging)
- Archive older logs more aggressively
- Delete test/debug logs
- Compress old logs

**Estimated Savings:** $10-20/month if cleaned

---

### 4. **UNUSED / ORPHANED RESOURCES** (Potentially $50-100+/month)

**Specific Items to Check:**
- [ ] **DynamoDB tables** - Are we using all of them?
  - `algo-contact-rate-limit-dev`
  - `algo-token-blocklist-dev`
  - `algo_orchestrator_state` (Is this actively used?)
  
- [ ] **S3 buckets with old files**
  - code bucket: keeping 7-day old builds (needed?)
  - data bucket: keeping 7-day old staging data (cleanup?)
  - lambda artifacts: keeping old ZIPs

- [ ] **Lambda functions** - Unused or test lambdas?
  - Count: should be ~2-3 (API, Orchestrator, maybe 1 utility)
  - Any old test/debug ones?

- [ ] **Security groups** - Unused ones?
  - Each security group = negligible cost but indicates slop

- [ ] **RDS parameter groups** - Old ones left behind?

- [ ] **IAM roles** - Unused role definitions?

**To Check:**
```bash
# Lambda functions (list all)
aws lambda list-functions --region us-east-1 \
  --query 'Functions[].{name:FunctionName, modified:LastModified}' \
  --output table

# DynamoDB table metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedWriteCapacityUnits \
  --dimensions Name=TableName,Value=algo-contact-rate-limit-dev \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum

# S3 buckets - what's in code bucket?
aws s3 ls s3://algo-code-626216981288/ --recursive --summarize

# S3 buckets - what's in lambda artifacts?
aws s3 ls s3://algo-lambda-artifacts-626216981288/ --recursive --summarize
```

**Potential Fixes:**
- Delete unused Lambda functions
- Delete unused DynamoDB tables (if not used)
- Empty old S3 files (keep last 1-2 only)
- Clean up old IAM roles

**Estimated Savings:** $10-30/month if cleaned

---

### 5. **INEFFICIENT DATA IN DATABASE** (Potentially $50-150+/month)

**The Real Problem:**
You have ALL historical data + redundant copies. E.g.:
- `technical_data_daily` - How far back? 5+ years?
- `daily_price_data` - Storing EVERY single daily price forever
- `buy_sell_daily` - Storing EVERY signal ever generated
- Test/debug tables never deleted

**To Check:**
```sql
-- Find oldest data
SELECT table_name, 
  (SELECT min(date) FROM table_name) as oldest_data,
  (SELECT max(date) FROM table_name) as newest_data
FROM information_schema.tables
WHERE table_schema = 'public';

-- See actual sizes
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
  pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
  pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) as indexes_size
FROM pg_tables
WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

**Potential Fixes:**
- Archive data > 2 years old to S3 (keep only recent for queries)
- Delete test tables
- Delete duplicate tables
- Partition large tables by date

**Estimated Savings:** $50-150/month if archived

---

## **TOTAL REAL WASTE AUDIT**

| Category | Potential Savings | Difficulty | Priority |
|----------|-------------------|-----------|----------|
| RDS Storage Bloat | $20-50 | 🟡 Medium | 🔴 HIGH |
| Slow Loaders | $30-100 | 🔴 Hard | 🔴 HIGH |
| Logging Bloat | $10-20 | 🟢 Easy | 🟠 Medium |
| Unused Resources | $10-30 | 🟢 Easy | 🟠 Medium |
| Database Data Bloat | $50-150 | 🔴 Hard | 🔴 HIGH |
| **TOTAL POTENTIAL** | **$120-350/month** | — | — |

Combined with already-fixed $202/month = **$322-552/month total potential savings**

**That's $3,900-6,600/year additional beyond what we already fixed.**

---

## ACTION PLAN - PRIORITY ORDER

### IMMEDIATE (Today - 15 minutes each)
1. **DELETE stocks_test database** ✅ Need to execute
2. **Run VACUUM on RDS** (reclaim dead space)
   ```sql
   VACUUM ANALYZE;
   ```
3. **Check table sizes** (find the biggest ones)
   ```sql
   SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(...))
   ```

### THIS WEEK (30 min-2 hours each)
1. **Archive old data** (> 2 years) to S3
2. **Delete unused test tables**
3. **Drop unused indexes**
4. **Optimize slow queries** (SEC EDGAR loaders)

### THIS MONTH (2-4 hours each)
1. **Profile loader performance** (identify slow ones)
2. **Increase parallelism** (if safe)
3. **Compress old CloudWatch logs**
4. **Clean S3 buckets** (keep only recent)

---

## EXECUTION CHECKLIST

- [ ] **DELETE stocks_test** (2 min)
  - Command: `DROP DATABASE IF EXISTS stocks_test;`
  
- [ ] **VACUUM RDS** (5 min)
  - Command: `VACUUM ANALYZE;`
  
- [ ] **Check table sizes** (5 min)
  - Find what's taking up space
  
- [ ] **Delete test tables** (10 min)
  - Anything with "test", "debug", "tmp" in name
  
- [ ] **Check DynamoDB usage** (5 min)
  - Are tables actually being used?

- [ ] **Audit slowest loaders** (15 min)
  - CloudWatch logs for runtime

- [ ] **Profile API performance** (15 min)
  - Any slow queries?

- [ ] **Check S3 bucket sizes** (5 min)
  - How much old data?

---

**Mission: Find and eliminate ALL the real waste. Not just the easy $200, but the FULL $400-500/month.**

This is where the money actually lives - in database bloat, inefficient queries, and unnecessary data storage.

Let's finish the job properly.

