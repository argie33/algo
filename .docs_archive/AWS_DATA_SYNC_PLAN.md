# AWS Data Sync Plan — Get Local Data to RDS

## Current Status (Local)

✅ **Verified Local Database:**
- 22.8 million price records
- 4,965 unique symbols
- Data from 1962-2026 (latest: 2026-04-24)
- All 5 parallel loaders working without errors
- Execution time: ~10 minutes for full 4,965 symbols

## Three Options to Get Data to AWS

### Option 1: Direct Database Restore (Fastest - Recommended)

```bash
# 1. Dump local database
pg_dump -h localhost -U stocks -d stocks --no-owner --no-privileges \
  --schema public --format custom \
  --file stocks_backup.dump

# 2. Upload to S3
aws s3 cp stocks_backup.dump s3://your-bucket/dumps/

# 3. Restore to AWS RDS
pg_restore -h RDS_ENDPOINT -U stocks -d stocks \
  -j 4 stocks_backup.dump
```

**Pros:** One-time operation, instant data
**Cons:** Need RDS instance already running
**Time:** 5-15 minutes

### Option 2: Run Loaders in AWS (Recommended for Ongoing)

```bash
# 1. Ensure AWS RDS is configured
#    (VPC, security groups allowing Lambda access)

# 2. Deploy Lambda with existing loaders
#    (see PARALLEL_LOADING_GUIDE.md)

# 3. Run initial full load in AWS
aws lambda invoke \
  --function-name LoadPriceDailyOrchestrator \
  --invocation-type RequestResponse \
  response.json

# 4. Check status
cat response.json
```

**Pros:** Uses cloud-native approach, scalable
**Cons:** Need AWS setup first
**Time:** 1-2 hours setup + 30 min initial load

### Option 3: Data Export + Import

```bash
# Export just price_daily
psql -h localhost -U stocks -d stocks \
  --command "COPY price_daily TO STDOUT FORMAT CSV HEADER" \
  > price_daily.csv

# Upload to S3
aws s3 cp price_daily.csv s3://your-bucket/data/

# Load into RDS via COPY
psql -h RDS_ENDPOINT -U stocks -d stocks \
  --command "COPY price_daily FROM 's3://your-bucket/data/price_daily.csv' CSV HEADER"
```

**Pros:** Flexible, can selectively sync
**Cons:** Slower than restore, large CSV file
**Time:** 20-30 minutes

---

## Prerequisites for AWS

Before syncing data, ensure:

1. **AWS RDS Instance** running PostgreSQL 14+
   ```bash
   aws rds describe-db-instances --query 'DBInstances[*].[DBInstanceIdentifier,Engine]'
   ```

2. **VPC/Security Group** allows local access (for restore) or Lambda access (for loaders)
   ```bash
   # Test connection
   psql -h RDS_ENDPOINT -U stocks -d stocks -c "SELECT VERSION();"
   ```

3. **AWS Credentials** configured locally
   ```bash
   aws sts get-caller-identity
   ```

4. **IAM Role** for Lambda with RDS access
   ```bash
   aws iam list-roles | grep -i lambda
   ```

---

## Recommended Flow

1. **Confirm RDS exists and is accessible**
   ```bash
   aws rds describe-db-instances
   ```

2. **Dump local database**
   ```bash
   pg_dump -h localhost -U stocks -d stocks --format custom \
     > stocks_full.dump
   ls -lh stocks_full.dump  # Should be ~2-5GB
   ```

3. **Restore to AWS (Option 1)**
   ```bash
   pg_restore -h YOUR_RDS_ENDPOINT -U stocks \
     -d stocks stocks_full.dump
   ```

4. **Verify data arrived**
   ```bash
   psql -h YOUR_RDS_ENDPOINT -U stocks -d stocks \
     -c "SELECT COUNT(*) FROM price_daily;"
   ```

5. **Deploy loaders to Lambda** (PARALLEL_LOADING_GUIDE.md)

6. **Schedule daily updates** (AWS_OPTIMIZED_LOADING_DESIGN.md)

---

## Expected Times

| Operation | Duration | Notes |
|-----------|----------|-------|
| Local dump | 5-10 min | 22.8M rows = ~2-5GB |
| S3 upload | 10-20 min | Depends on network |
| RDS restore | 5-15 min | Parallel restore |
| Verify | <1 min | COUNT(*) check |
| **Total** | **25-45 min** | One-time operation |

---

## Next Steps

1. **Check if RDS already exists**
   ```bash
   aws rds describe-db-instances --query 'DBInstances[*].[DBInstanceIdentifier,Endpoint.Address]'
   ```

2. **If yes:** Proceed with Option 1 (dump + restore)

3. **If no:** 
   - Create RDS instance first
   - Or use Option 2 (Lambda loaders from scratch)

4. **After data sync:** Deploy loaders and schedule daily runs (see PARALLEL_LOADING_GUIDE.md)

---

## Commands Ready to Copy-Paste

### Dump Local Database
```bash
cd ~/code/algo
pg_dump -h localhost -U stocks -d stocks \
  --no-owner --no-privileges --format custom \
  > stocks_backup_$(date +%Y%m%d).dump

ls -lh stocks_backup_*.dump
```

### Check RDS Connectivity
```bash
psql -h YOUR_RDS_ENDPOINT \
  -U stocks \
  -d stocks \
  -c "SELECT COUNT(*) FROM price_daily;" 2>/dev/null || \
  echo "Cannot connect - check security groups"
```

### Get RDS Endpoint
```bash
aws rds describe-db-instances \
  --db-instance-identifier stocks-db \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text
```
