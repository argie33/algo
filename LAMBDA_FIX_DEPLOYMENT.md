# Lambda API Fix - Deployment Guide

## Problem Fixed
**AWS Lambda returning 503 errors for all API requests with error message:**
```
AttributeError: module 'routes.algo' has no attribute 'handle'
```

## Root Cause
The `handle` function in `lambda/api/routes/algo.py` had **8-space indentation** instead of **4-space indentation**, making it appear as a nested function rather than a module-level function that the Lambda router expected.

## Fix Applied
✅ **Corrected the indentation** in `lambda/api/routes/algo.py`:
- `handle()` function: Changed from 8 spaces to 4 spaces
- `_dispatch()` function: Changed from 8 spaces to 4 spaces  
- All nested blocks adjusted accordingly
- Restored missing import: `set_statement_timeout_from_config`

**File:** `lambda/api/routes/algo.py`

## Deployment Steps

### Option 1: GitHub Actions Deployment (Recommended)
1. Push the code to main branch (if not already pushed)
2. Trigger the "Deploy Application Code" workflow manually:
   ```
   gh workflow run deploy-code.yml
   ```
   OR
   Go to: https://github.com/argie33/algo/actions/workflows/deploy-code.yml

3. Wait for the workflow to complete
4. The Lambda will be updated with the fixed code

### Option 2: Manual AWS CLI Deployment
Since the `algo-developer` user doesn't have Lambda update permissions, use the GitHub Actions role:

```bash
aws lambda update-function-code \
  --function-name algo-api-dev \
  --zip-file fileb://terraform/lambda_api.zip \
  --region us-east-1
```

**Note:** This requires AWS credentials with `lambda:UpdateFunctionCode` permission.

### Option 3: Terraform Deployment
```bash
cd terraform
terraform apply -target=aws_lambda_function.api
```

## Verification

### 1. Local Testing (Already Done ✅)
```bash
python3 -c "import sys; sys.path.insert(0, 'lambda/api'); from routes import algo; print('✓ Module imports correctly')"
```

### 2. AWS Lambda Test (After Deployment)
Test the Lambda with a simple /api/algo/markets request:
```bash
aws lambda invoke \
  --function-name algo-api-dev \
  --payload '{"rawPath":"/api/algo/markets","requestContext":{"http":{"method":"GET"}},"headers":{"origin":"https://d2u93283nn45h2.cloudfront.net"}}' \
  response.json
```

Expected: **statusCode: 200** with market data (not 500 with handle error)

### 3. Dashboard Test (After Deployment)
1. Open: https://d2u93283nn45h2.cloudfront.net (or your CloudFront domain)
2. Navigate to Market Health page
3. Verify data loads (no "API Connection Issue" errors)
4. Check browser console: No 503 errors

## Package Information
- **Built:** terraform/lambda_api.zip (22 MB, 2379 files)
- **Includes:** lambda/api + config + utils directories
- **Python Runtime:** 3.12
- **Status:** Ready for deployment

## Timeline
- **Issue Identified:** 2026-06-13
- **Root Cause Found:** Invalid module indentation blocking handle() function import
- **Fix Applied:** 2026-06-13 15:00 UTC
- **Package Built:** 2026-06-13 15:12 UTC
- **Pending:** AWS Lambda deployment

## Related Files
- `lambda/api/routes/algo.py` - Fixed file
- `terraform/lambda_api.zip` - Built deployment package
- GitHub Actions workflow: `.github/workflows/deploy-code.yml`
