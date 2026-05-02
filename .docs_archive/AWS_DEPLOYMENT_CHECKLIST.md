# AWS Deployment Checklist - Unified DatabaseHelper Architecture

## ✅ Pre-Deployment Status

### Infrastructure Files
- [x] **Dockerfile** - Unified image includes all 54 refactored loaders + db_helper.py
- [x] **db_helper.py** - DatabaseHelper abstraction with S3 bulk loading support
- [x] **requirements.txt** - All Python dependencies specified
- [x] **All 54 loaders** - Refactored to use DatabaseHelper pattern
- [x] **GitHub Actions workflow** - Updated for unified Docker builds

### Local Verification
- [x] DatabaseHelper imports successfully
- [x] All 54 loaders import without errors
- [x] Docker Dockerfile syntax valid
- [x] requirements.txt contains all dependencies

---

## 🚀 AWS Deployment Steps

### Step 1: AWS Prerequisites (One-Time Setup)

**1A. Enable RDS aws_s3 Extension**
```sql
-- Connect to RDS as postgres user, stocks database
CREATE EXTENSION IF NOT EXISTS aws_s3 CASCADE;
```

**1B. Create IAM Role for RDS S3 Access**
```bash
# Create role named: RDSBulkInsertRole
# Trust policy: Allow RDS to assume the role
# Permission: s3:GetObject, s3:ListBucket on stocks-app-data bucket

# Then add inline policy:
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::stocks-app-data",
        "arn:aws:s3:::stocks-app-data/*"
      ]
    }
  ]
}
```

**1C. Create S3 Bucket**
```bash
aws s3 mb s3://stocks-app-data --region us-east-1
```

**1D. Verify ECS Task Definition Has Environment Variables**

The CloudFormation stack should set these environment variables in ECS task definitions:
```bash
USE_S3_STAGING=true
S3_STAGING_BUCKET=stocks-app-data
RDS_S3_ROLE_ARN=arn:aws:iam::ACCOUNT:role/RDSBulkInsertRole
DB_HOST=stocks.c...rds.amazonaws.com  # RDS endpoint
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=<from AWS Secrets Manager>
DB_NAME=stocks
```

### Step 2: Push Code to GitHub

```bash
# Commit any changes
git add .
git commit -m "Update for unified DatabaseHelper deployment"

# Push to main branch
git push origin main
```

This will trigger the GitHub Actions workflow automatically.

### Step 3: Monitor GitHub Actions Workflow

The workflow does this automatically:

1. **detect-changes** - Identifies which loaders changed
2. **deploy-infrastructure** - Creates/updates CloudFormation stacks (RDS, ECS, etc.)
3. **Build unified Docker image** - Builds single image with all 54 loaders
4. **Push to ECR** - Stores image in AWS Elastic Container Registry
5. **Execute loaders in parallel** - Runs detected loaders as ECS Fargate tasks

### Step 4: Verify Deployment

**4A. Check CloudWatch Logs**
```bash
# Follow loader execution logs
aws logs tail /aws/ecs/stocks-loaders --follow

# Look for these success indicators:
# "Using S3 bulk loading (10x faster)"  <- S3 optimization is active
# "[OK] Inserted 10000 rows"            <- Data loading succeeded
```

**4B. Verify Data in RDS**
```sql
-- Connect to RDS and check table counts
SELECT 'price_daily' as table_name, COUNT(*) as rows FROM price_daily
UNION ALL
SELECT 'buy_sell_daily', COUNT(*) FROM buy_sell_daily
UNION ALL
SELECT 'annual_balance_sheet', COUNT(*) FROM annual_balance_sheet;

-- Check recent data (should have TODAY's date)
SELECT MAX(date) FROM price_daily;
SELECT MAX(date) FROM buy_sell_daily;
```

**4C. Verify S3 Staging Bucket**
```bash
# Check S3 for staging files
aws s3 ls s3://stocks-app-data/

# Verify files are cleaned up after each loader
# (Files should be temporary, cleaned after COPY completes)
```

---

## 🔧 How the Unified Architecture Works

### DatabaseHelper Pattern

All loaders follow this pattern:

```python
from db_helper import DatabaseHelper

def main():
    db_config = get_db_config()  # Reads from env vars or secrets
    db = DatabaseHelper(db_config)
    
    # Fetch data
    rows = fetch_data()
    
    # Single insert call - DatabaseHelper chooses best method
    inserted = db.insert(
        table_name='price_daily',
        columns=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume'],
        rows=rows
    )
    db.close()
    print(f"Inserted {inserted} rows")

if __name__ == '__main__':
    main()
```

### DatabaseHelper Decision Logic

```
DatabaseHelper.insert()
    ↓
    └─ if USE_S3_STAGING=true and RDS_S3_ROLE_ARN set:
    │      Use S3 bulk COPY (10-15x faster) ✅
    │      1. Upload rows to S3 as CSV
    │      2. Use RDS aws_s3 extension to COPY from S3
    │      3. Delete S3 staging files
    │
    └─ else:
           Use standard inserts (reliable fallback) ✅
           1. Batch insert in 500-row chunks
           2. Handle duplicate keys gracefully
           3. No external dependencies
```

---

## 📊 Expected Performance

### S3 Bulk Loading Active (AWS)
- **Price Daily** (1.2M rows): 30-45 seconds
- **Buy/Sell Daily** (250k rows): 30 seconds
- **All loaders**: ~10 minutes total

### Standard Inserts (Local or Fallback)
- **Price Daily**: 5-10 minutes
- **Buy/Sell Daily**: 3-4 minutes
- **All loaders**: 45+ minutes total

---

## 🐛 Troubleshooting

### "Using standard inserts (S3 bulk load failed...)"
**Problem:** S3 optimization not activating
**Solution:** 
1. Verify `USE_S3_STAGING=true` in CloudWatch logs
2. Verify `RDS_S3_ROLE_ARN` is set
3. Verify RDS has `aws_s3` extension: `SELECT * FROM pg_extension WHERE extname='aws_s3';`
4. Check RDS security group allows S3 access

### "ERROR: Could not connect to database"
**Problem:** RDS connection failing
**Solution:**
1. Verify RDS security group allows ECS Fargate (0.0.0.0/0 for now, or specific ECS SG)
2. Verify DB_HOST is correct RDS endpoint
3. Check CloudWatch logs for exact error

### "ERROR: Permission denied on aws_s3.table_import_from_s3"
**Problem:** RDS role doesn't have S3 permissions
**Solution:**
1. Create RDSBulkInsertRole with S3 access
2. Add to RDS instance: `ALTER DATABASE stocks SET rds.s3_role='arn:aws:iam::ACCOUNT:role/RDSBulkInsertRole';`

### "Loader didn't produce any output"
**Problem:** Loader may be hanging or crashing silently
**Solution:**
1. Check CloudWatch for errors
2. Check ECS task status: `aws ecs describe-tasks --cluster stocks-cluster --tasks <task-arn>`
3. Verify data source (yfinance, API key, etc.) is working

---

## ✨ Deployment Summary

### What Gets Deployed
1. **Unified Docker Image** - Single 500MB image with all 54 loaders
2. **DatabaseHelper Abstraction** - Handles S3 vs standard insert logic
3. **Environment Variables** - For S3 staging and DB connection
4. **ECS Fargate Tasks** - Run loaders in parallel, max 3 at a time

### Benefits vs Old System
- **10-15x faster** for high-volume loaders (S3 bulk COPY)
- **Single Docker image** instead of 54 per-loader images
- **Automatic S3 optimization** - no loader code changes needed
- **Graceful fallback** - works even if S3 fails
- **Consistent pattern** - all loaders follow same architecture

### Next Actions
1. Push changes to GitHub (triggers workflow automatically)
2. Monitor CloudWatch logs for loader execution
3. Verify data counts in RDS match expected volumes
4. Celebrate 10x performance improvement! 🚀

---

## 📚 Related Documentation

- `README_DEPLOYMENT.md` - Quick start guide
- `LOADER_BEST_PRACTICES.md` - Architectural patterns
- `AWS_BEST_PRACTICES.md` - AWS optimization guide
- `AWS_DEPLOYMENT_GUIDE.md` - Detailed setup instructions

