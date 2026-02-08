# AWS Earnings Data Sync Plan

## Current Status (LOCAL)
✅ **Earnings History**: 2,354 records for 607 symbols (in progress)
⏳ **Earnings Estimates**: 0 records (loader running)
✅ **Earnings Surprises**: 3,835 records (complete)
✅ **Earnings Estimate Revisions**: 690 records (complete)
✅ **Earnings Estimate Trends**: 712 records (complete)

## Local Data Loaders (Running)
1. `loadearningshistory.py` - Batch 6+/967 (FIXED: removed symbol filtering)
2. `load_earnings_estimates_efficient.py` - Running in parallel

## AWS Deployment Steps

### 1. Schema Verification (NO CHANGES NEEDED)
- ✅ earnings_history: 7 columns (matches local)
- ✅ earnings_estimates: 9 columns (matches local)
- ✅ earnings_surprises: 12 columns (matches local)
- ✅ All tables have proper indexes

### 2. ECS Task Definitions (ALREADY DEFINED)
Located in `template-app-ecs-tasks.yml`:
- EarningsHistoryTaskDefinition
- EarningsEstimateTaskDefinition
- EarningsMetricsTaskDefinition

### 3. AWS RDS Data Sync Strategy
**Option A: Full Reload (Recommended)**
```bash
# 1. Clear existing earnings data in AWS RDS
# 2. Run ECS tasks to reload from yfinance
# 3. Verify data completeness
```

**Option B: Delta Sync**
```bash
# 1. Export local data to CSV
# 2. Upload to S3
# 3. Use RDS COPY to import
```

### 4. Data Validation
After sync, verify in AWS:
```sql
-- Check earnings_history
SELECT COUNT(*) as total_records, COUNT(DISTINCT symbol) as symbols
FROM earnings_history;

-- Should match or exceed: 2,354 records, 607+ symbols
```

### 5. API Testing
- Test /api/earnings/info endpoint
- Test /api/earnings/calendar endpoint
- Verify data appears in frontend

## Environment Variables for AWS
```
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:626216981288:secret:rds-stocks-secret-ABCDE
AWS_REGION=us-east-1
```

## Files Modified
- ✏️ loadearningshistory.py - Removed symbol filtering
- ✨ load_earnings_estimates_efficient.py - New efficient loader

## Next Steps
1. ✅ Complete local earnings data load (in progress)
2. ⏳ Verify earnings estimates complete  
3. ⏳ Sync local DB to AWS RDS
4. ⏳ Run ECS earnings loaders in AWS
5. ⏳ Verify API returns data from AWS
