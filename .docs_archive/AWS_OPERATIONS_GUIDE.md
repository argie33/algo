# AWS Operations Guide - Stock Analytics Data Loaders

## System Overview

The stock analytics system runs **54 refactored data loaders** on AWS using:
- **ECS Fargate** for execution (no servers to manage)
- **RDS PostgreSQL** for data storage
- **S3** for staging bulk data (10x faster than direct inserts)
- **DatabaseHelper** abstraction layer (handles all cloud complexity)

---

## 🟢 Healthy System Indicators

### CloudWatch Logs Should Show:

```
[LOADER] loadpricedaily.py starting...
[DB] Connecting to RDS...
[DATA] Fetched 12000 prices for 4969 symbols
[INSERT] Using S3 bulk loading (10x faster)
[S3] Uploaded 120MB to s3://stocks-app-data/...
[RDS] COPY FROM S3 succeeded
[S3] Cleaned up staging files
[INSERT] Inserted 12000 rows in 42 seconds
[OK] Loader completed successfully
```

### CloudWatch Metrics:
- **Task duration**: 30-90 seconds per loader
- **Success rate**: 100% (or ~95% with API variance)
- **Error logs**: None (or only warnings)
- **S3 staging files**: Empty after each loader (auto-cleaned)

### RDS Checks:
```sql
-- All tables should have recent data
SELECT table_name, 
       (SELECT MAX(date) FROM public.table_name) as latest_date,
       (SELECT COUNT(*) FROM public.table_name) as total_rows
FROM information_schema.tables 
WHERE table_schema='public' 
ORDER BY table_name;

-- Data should be fresh (within 24 hours)
SELECT MAX(date) FROM price_daily;      -- Today
SELECT MAX(date) FROM buy_sell_daily;   -- Today
SELECT MAX(date) FROM earnings_history; -- Recent
```

---

## 🔴 Common Issues & Fixes

### Issue 1: Loaders Are Slow (>5 minutes)

**Symptom:**
```
[INSERT] Using standard inserts (no S3)...
[WARN] S3 bulk load not available
[INSERT] Inserted 10000 rows in 8 minutes
```

**Root Cause:** S3 bulk loading not activated

**Fix:**
```bash
# Check environment variables in ECS task definition
aws ecs describe-task-definition --task-definition loadpricedaily:1 \
  | jq '.taskDefinition.containerDefinitions[0].environment'

# Should show:
# USE_S3_STAGING=true
# S3_STAGING_BUCKET=stocks-app-data
# RDS_S3_ROLE_ARN=arn:aws:iam::...

# If missing, update task definition via CloudFormation console
# Or redeploy via GitHub Actions
```

### Issue 2: RDS Connection Fails

**Symptom:**
```
[ERROR] psycopg2.OperationalError: could not connect to server
[ERROR] could not translate host name "stocks.c...rds.amazonaws.com" to address
```

**Root Cause:** RDS security group or networking issue

**Fix:**
```bash
# 1. Check RDS security group allows ECS
aws rds describe-db-security-groups --db-security-group-name default

# 2. Verify ECS subnet has route to RDS
aws ec2 describe-route-tables --filters Name=vpc-id,Values=vpc-xxx

# 3. Test RDS connectivity from ECS task
# (AWS docs: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.html)

# 4. If stuck: redeploy infrastructure
git push origin main  # Triggers CloudFormation redeploy
```

### Issue 3: S3 Permission Denied

**Symptom:**
```
[ERROR] botocore.exceptions.ClientError: An error occurred (AccessDenied)
[ERROR] User: arn:aws:iam::...  is not authorized to perform: s3:GetObject
```

**Root Cause:** RDSBulkInsertRole missing S3 permissions

**Fix:**
```bash
# 1. Check role policy
aws iam get-role-policy --role-name RDSBulkInsertRole --policy-name s3-access

# 2. Add permissions if missing
aws iam put-role-policy --role-name RDSBulkInsertRole \
  --policy-name s3-access \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::stocks-app-data*"]
    }]
  }'

# 3. Restart failed loader task
```

### Issue 4: OOM or Timeout Errors

**Symptom:**
```
[ERROR] Task stopped: OutOfMemory
[ERROR] Task stopped: CannotStartContainerError
[WARN] Timeout waiting for 500MB CSV file...
```

**Root Cause:** 
- CSV file too large for available memory
- Slow network upload to S3

**Fix:**
```bash
# 1. Increase ECS task memory in CloudFormation template
# Change: memory: 512 -> memory: 2048

# 2. Check S3 upload speed
# Can reduce batch size in db_helper.py if needed

# 3. Monitor task definition resource limits
aws ecs describe-task-definition --task-definition loadpricedaily:1 \
  | jq '.taskDefinition.memory, .taskDefinition.cpu'
```

---

## 📊 Monitoring Dashboard Commands

### Real-Time Loader Status
```bash
# Watch active loaders
watch -n 5 'aws ecs list-tasks --cluster stocks-cluster \
  | jq .taskArns[] | xargs -I {} aws ecs describe-tasks \
  --cluster stocks-cluster --tasks {} \
  | jq ".tasks[] | {name: .containerInstanceArn, status}"'

# Count running tasks
aws ecs list-tasks --cluster stocks-cluster --desired-status RUNNING | jq '.taskArns | length'
```

### Recent Logs
```bash
# Last 50 lines of all loaders
aws logs tail /aws/ecs/stocks-loaders --lines 50

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/ecs/stocks-loaders \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s)000

# Stream specific loader
aws logs tail /aws/ecs/stocks-loaders \
  --log-stream-name-prefix "stocks/loadpricedaily" \
  --follow
```

### Data Freshness
```bash
# Check when data was last loaded
psql -h $RDS_ENDPOINT -U stocks -d stocks << 'SQL'
SELECT 
  'price_daily' as table_name,
  MAX(date) as latest_date,
  EXTRACT(EPOCH FROM NOW() - MAX(date))::int / 3600 as hours_ago,
  COUNT(*) as total_rows
FROM price_daily
UNION ALL
SELECT 'buy_sell_daily', MAX(date), 
  EXTRACT(EPOCH FROM NOW() - MAX(date))::int / 3600, COUNT(*)
FROM buy_sell_daily
UNION ALL
SELECT 'annual_balance_sheet', MAX(quarter), 
  EXTRACT(EPOCH FROM NOW() - MAX(quarter))::int / 86400, COUNT(*)
FROM annual_balance_sheet
ORDER BY 1;
SQL
```

### S3 Staging Health
```bash
# S3 bucket should be nearly empty (files auto-cleaned)
aws s3 ls s3://stocks-app-data/ --recursive | head -20

# If files accumulate, loader may be crashing
# Check CloudWatch logs for errors
```

---

## 🔧 Common Operational Tasks

### Manually Run a Specific Loader

```bash
# 1. Get latest task definition
TASK_DEF=$(aws ecs describe-services \
  --cluster stocks-cluster \
  --services stocks-app-service \
  | jq -r '.services[0].taskDefinition')

# 2. Run specific loader
aws ecs run-task \
  --cluster stocks-cluster \
  --task-definition $TASK_DEF \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-zzz],assignPublicIp=ENABLED}" \
  --overrides '{
    "containerOverrides": [{
      "name": "stocks-loader",
      "command": ["loadpricedaily.py"]
    }]
  }'
```

### Re-Run Failed Loaders

```bash
# GitHub Actions automatically retries on push
# To manually retry:

# 1. Make a commit that touches the loader
git touch loadpricedaily.py
git commit -m "Retry loadpricedaily"
git push origin main

# This triggers the workflow to rebuild and re-run
```

### Update Environment Variables

```bash
# 1. Edit CloudFormation parameter in template
# 2. Redeploy via GitHub Actions
git push origin main

# OR manually update via CLI:
aws ecs update-service \
  --cluster stocks-cluster \
  --service stocks-app-service \
  --force-new-deployment
```

### Check Data Quality

```bash
# Run validation query
psql -h $RDS_ENDPOINT -U stocks -d stocks << 'SQL'
-- Check for gaps in price data
SELECT symbol, COUNT(*) as count, 
       MAX(date) as latest, MIN(date) as oldest
FROM price_daily
GROUP BY symbol
HAVING COUNT(*) < 1000  -- Symbols with <1000 rows
ORDER BY count;

-- Check buy/sell signals
SELECT signal, COUNT(*) as count FROM buy_sell_daily GROUP BY signal;

-- Check for duplicates
SELECT symbol, date, COUNT(*) as cnt
FROM price_daily
GROUP BY symbol, date
HAVING COUNT(*) > 1;
SQL
```

---

## 🚀 Scaling & Performance Tuning

### Enable Parallel Execution
The system already runs up to 3 loaders in parallel. To increase:

```yaml
# In GitHub Actions workflow:
strategy:
  max-parallel: 5  # Increase from 3 to 5
```

**⚠️ Warning:** Only increase if RDS can handle the load. Monitor:
- RDS CPU (should stay <70%)
- RDS connections (max ~60 before issues)
- Network bandwidth (watch for throttling)

### S3 Optimization

Current: 500-row batches, 100MB CSV files

To optimize further:
```python
# In db_helper.py, adjust:
BATCH_SIZE = 1000      # Larger batches
S3_UPLOAD_TIMEOUT = 30 # Seconds before giving up on S3
```

Tradeoffs:
- Larger batches = faster but more memory
- Faster timeout = fallback to standard inserts sooner

### RDS Scaling

If hitting capacity:
```bash
# 1. Increase storage (automatic with auto-scaling)
aws rds modify-db-instance \
  --db-instance-identifier stocks \
  --max-allocated-storage 1000 \
  --apply-immediately

# 2. Upgrade instance class (may require downtime)
aws rds modify-db-instance \
  --db-instance-identifier stocks \
  --db-instance-class db.t3.large \
  --apply-immediately
```

---

## 📈 Metrics to Watch

### Health Score
Calculate daily:
```
Health = (successful_loaders / total_loaders) * 100
- 100% = All loaders completed successfully
- 95%+ = Healthy (some API variance acceptable)
- <90% = Investigate failures
```

### Performance Score
```
Speed = (actual_time / expected_time) * 100
- Expected with S3: ~10 minutes total
- Expected without S3: ~45 minutes total
- <120% = Good
- >200% = Investigate slowness
```

### Data Freshness Score
```
Freshness = loaders_with_today_data / total_loaders
- 100% = All tables updated today
- 50%+ = Acceptable
- <50% = Stale data warning
```

---

## 🆘 Emergency Procedures

### Complete System Reset

```bash
# 1. Delete old tasks and logs
aws ecs list-tasks --cluster stocks-cluster --desired-status RUNNING | \
  jq -r '.taskArns[]' | \
  xargs -I {} aws ecs stop-task --cluster stocks-cluster --task {}

# 2. Clear database if corrupted
# WARNING: This deletes all data!
psql -h $RDS_ENDPOINT -U stocks -d stocks << 'SQL'
TRUNCATE TABLE price_daily CASCADE;
TRUNCATE TABLE buy_sell_daily CASCADE;
-- ... truncate all tables
SQL

# 3. Restart loaders from clean state
git commit --allow-empty -m "Reset system"
git push origin main
```

### Rollback to Previous Stable Version

```bash
# 1. Find last stable commit
git log --oneline | head -5

# 2. Revert
git revert <commit-hash>
git push origin main

# GitHub Actions will automatically deploy previous version
```

---

## 📞 Support Resources

- **CloudWatch Logs**: `/aws/ecs/stocks-loaders`
- **ECS Console**: https://console.aws.amazon.com/ecs/
- **RDS Console**: https://console.aws.amazon.com/rds/
- **GitHub Actions**: Repository → Actions → deploy-app-stocks

Contact: [Your team contact info]

