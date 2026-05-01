# AWS Deployment Verification Checklist

## ✅ Code Refactoring Status

**Total Loaders:** 60
**Refactored to DatabaseHelper:** 54 (90%)
**Status:** READY FOR AWS DEPLOYMENT

## 🔧 Pre-Deployment Setup Required

### 1. RDS Configuration (One-Time, Production)
```bash
# Connect to RDS and run:
psql -h <RDS-ENDPOINT> -U postgres -d stocks << SQL
CREATE EXTENSION IF NOT EXISTS aws_s3 CASCADE;
SELECT * FROM pg_extension WHERE extname = 'aws_s3';
SQL
```

### 2. IAM Role Setup (One-Time, Production)
Create `RDSBulkInsertRole` with:
- **Trust:** Allow rds.amazonaws.com to assume
- **S3 Permissions:** s3:GetObject, s3:PutObject, s3:ListBucket, s3:DeleteObject on stocks-app-data/*
- **Attach to RDS:** Go to RDS console → Modify DB instance → Associated IAM roles

### 3. Environment Variables in ECS/Lambda

Add to all task definitions:
```
AWS_REGION=us-east-1
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:rds-stocks
S3_STAGING_BUCKET=stocks-app-data
RDS_S3_ROLE_ARN=arn:aws:iam::ACCOUNT:role/RDSBulkInsertRole
USE_S3_STAGING=true
```

## 🧪 Testing Plan

### Phase 1: Local Validation (Before AWS)
```bash
# 1. Test DatabaseHelper locally (no S3)
export USE_S3_STAGING=false
python3 test_database_helper.py
# Should pass all tests

# 2. Test single refactored loader
python3 loadpricedaily.py
# Should complete in 3-5 minutes, load ~500k rows
```

### Phase 2: AWS Validation (ECS Fargate)
```bash
# 1. Deploy single loader task with refactored code
# 2. Monitor CloudWatch logs for:
#    - "Starting loader..."
#    - "Using S3 bulk loading (1000x faster)" OR "Using standard inserts"
#    - "Completed: X rows inserted in Ys"

# 3. Verify row counts in RDS
psql -h <RDS> -U stocks -d stocks << SQL
SELECT COUNT(*) FROM price_daily;
SELECT COUNT(*) FROM buy_sell_daily;
SQL

# 4. Measure execution time and verify 10x speedup
```

### Phase 3: Full Deployment (All 54 Loaders)
```bash
# 1. Update CloudFormation with new ECS task definitions
# 2. Deploy all loaders to ECS
# 3. Monitor each loader's execution
# 4. Verify all tables are populated
# 5. Compare performance vs baseline
```

## 📊 Success Criteria

### Data Integrity
- [ ] All refactored loaders populate correct table
- [ ] Row counts match expected (e.g., 5000 symbols × 250 days = 1.25M rows)
- [ ] No data type mismatches (string where int, etc.)
- [ ] Duplicate key handling works (ON CONFLICT is respected)

### Performance
- [ ] S3 bulk loading is FASTER than standard inserts
- [ ] At least 6x speedup (S3 mode vs standard mode)
- [ ] Typical daily load completes in <15 minutes (all loaders)
- [ ] CloudWatch shows S3 operations in logs

### Reliability
- [ ] No crashes or errors in CloudWatch logs
- [ ] Graceful fallback from S3 to standard if S3 fails
- [ ] Proper error logging for debugging
- [ ] Database connections properly closed

## 🚨 Common Issues & Fixes

### Issue: "S3 extension not found"
**Fix:** Run `CREATE EXTENSION aws_s3 CASCADE` as postgres user on RDS

### Issue: "Permission denied uploading to S3"
**Fix:** Verify RDS has assumed the RDSBulkInsertRole and role has s3:PutObject

### Issue: Loaders complete but with 0 rows
**Fix:** Check that data is being fetched (API issues?) and row tuples are correct

### Issue: Standard insert used instead of S3
**Check:**
1. USE_S3_STAGING=true is set
2. RDS_S3_ROLE_ARN is correct
3. CloudWatch logs for fallback message

## 📋 Deployment Checklist

### Pre-Deployment
- [ ] All 54 loaders refactored to use DatabaseHelper
- [ ] test_database_helper.py passes locally
- [ ] Single refactored loader tested locally
- [ ] AWS credentials configured
- [ ] RDS endpoint is accessible

### Infrastructure (AWS)
- [ ] RDS aws_s3 extension enabled
- [ ] RDSBulkInsertRole created with correct policies
- [ ] S3 bucket (stocks-app-data) exists and is writable
- [ ] ECS task execution role has Secrets Manager access
- [ ] VPC/Security groups allow RDS + S3 access

### Deployment (ECS/Lambda)
- [ ] Docker image includes refactored loaders and db_helper.py
- [ ] Task definitions updated with environment variables
- [ ] All 54 loaders included in image
- [ ] Cloudwatch Log Group exists
- [ ] IAM roles attached to task execution role

### Validation (Post-Deployment)
- [ ] Run one loader and monitor CloudWatch
- [ ] Verify S3 staging bucket has files (if S3 enabled)
- [ ] Check RDS for new data
- [ ] Measure execution time
- [ ] Verify 10x speedup

## 🎯 Expected Results

**Without S3 (baseline):**
- 5000 symbols = 5-10 minutes
- 250k signals = 3-4 minutes
- Total pipeline = 45+ minutes

**With S3 (new):**
- 5000 symbols = 30-45 seconds (10-15x faster)
- 250k signals = 30 seconds (6-8x faster)
- Total pipeline = ~10 minutes (4-5x faster overall)

---

**Status:** Ready for AWS Deployment
**Last Updated:** 2026-05-01
