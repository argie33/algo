# URGENT: RDS Database Storage Full

## Issue
RDS instance `stocks` in `us-east-1a` has **STORAGE FULL** status causing complete service outage.

## Impact
- ✅ Lambda function syntax error FIXED
- ✅ Tests passing locally
- ✅ loadinfo.py optimized (75-85% cost savings)
- ❌ RDS database cannot accept connections (storage full)
- ❌ All API endpoints returning errors
- ❌ Frontend pages showing "Database error"
- ❌ loadinfo.py cannot write data

## Current Status
```
DBInstanceStatus: storage-full
AllocatedStorage: 20 GB
StorageType: gp2
MaxAllocatedStorage: None (no autoscaling enabled)
```

## Required Action
**IMMEDIATE**: Increase RDS storage allocation using AWS Console or admin credentials

### Option 1: AWS Console
1. Go to RDS Console: https://console.aws.amazon.com/rds/
2. Select database instance: `stocks`
3. Click "Modify"
4. Change "Allocated storage" from 20 GB to **30 GB** minimum
5. Check "Apply immediately"
6. Click "Modify DB instance"
7. Wait 5-10 minutes for modification to complete

### Option 2: AWS CLI (requires admin credentials)
```bash
aws rds modify-db-instance \
  --db-instance-identifier stocks \
  --region us-east-1 \
  --allocated-storage 30 \
  --max-allocated-storage 100 \
  --apply-immediately
```

### Option 3: Enable Storage Autoscaling (RECOMMENDED)
```bash
aws rds modify-db-instance \
  --db-instance-identifier stocks \
  --region us-east-1 \
  --max-allocated-storage 100 \
  --apply-immediately
```

## Current User Permissions
Reader user `arn:aws:iam::626216981288:user/reader` **CANNOT** modify RDS instances.
Need admin account with `rds:ModifyDBInstance` permission.

## After Storage Increase
1. RDS will automatically restart and accept connections
2. Lambda will reconnect automatically (no redeploy needed)
3. Frontend will start showing data again
4. loadinfo.py can resume loading data

## Prevention
Enable storage autoscaling (MaxAllocatedStorage) to prevent this in future.

## CloudFormation Template Updated ✅

**File**: `template-app-stocks.yml` (line 56-57)
```yaml
AllocatedStorage: 30      # Was: 20
MaxAllocatedStorage: 100  # New: enables autoscaling
```

## Deploy Stack Update (Admin Required)

**Option A: Using AWS Console**
1. Go to CloudFormation Console: https://console.aws.amazon.com/cloudformation/
2. Select stack: `stocks-app-stack`
3. Click "Update"
4. Choose "Replace current template"
5. Upload file: `template-app-stocks.yml`
6. Click "Next" through all pages (use existing parameters)
7. Check "I acknowledge that AWS CloudFormation might create IAM resources"
8. Click "Submit"
9. Wait 5-10 minutes for UPDATE_COMPLETE

**Option B: Using AWS CLI (Admin Credentials)**
```bash
cd /home/stocks/algo

aws cloudformation update-stack \
  --stack-name stocks-app-stack \
  --region us-east-1 \
  --template-body file://template-app-stocks.yml \
  --capabilities CAPABILITY_IAM \
  --parameters \
    ParameterKey=RDSUsername,UsePreviousValue=true \
    ParameterKey=RDSPassword,UsePreviousValue=true \
    ParameterKey=FREDApiKey,UsePreviousValue=true
```

Monitor progress:
```bash
aws cloudformation describe-stack-events \
  --stack-name stocks-app-stack \
  --region us-east-1 \
  --max-items 10
```

## Timeline
- Lambda syntax fixed: 2025-10-02 23:42 UTC ✅
- Storage full detected: 2025-10-02 23:47 UTC ⚠️
- Template updated: 2025-10-02 23:52 UTC ✅
- Waiting for admin to deploy stack update...
