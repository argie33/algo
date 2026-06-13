# Deployment Checklist — Production Readiness

**Status:** ✅ READY FOR AWS LAMBDA DEPLOYMENT

## Pre-Deployment Verification

- [x] Dev server launches on port 3001
- [x] Health endpoint responds correctly
- [x] API routes load without import failures
- [x] Database connection pool initializes
- [x] RDS connection successful (via Secrets Manager)
- [x] Orchestrator module imports successfully
- [x] Lambda handlers defined (`lambda_function.py` for API and Orchestrator)
- [x] Error handling is fail-fast (no silent fallbacks)
- [x] Financial data never returns placeholders
- [x] Admin rate limiting configured
- [x] Auth bypass working in dev mode

## AWS Deployment Steps

### 1. Prepare Lambda Packages

```bash
# API Lambda (REST endpoints)
cd lambda/api
zip -r ../../api-lambda.zip . -x "*.pyc" "__pycache__/*" ".pytest_cache/*"

# Orchestrator Lambda (scheduled EventBridge)
cd ../algo_orchestrator
zip -r ../../orchestrator-lambda.zip . -x "*.pyc" "__pycache__/*"

# Create Lambda Layer with dependencies
pip install -r requirements.txt -t python/lib/python3.11/site-packages
zip -r ../../deps-layer.zip python/
```

### 2. Configure AWS Lambda Functions

**API Lambda:**
- Function name: `algo-api-handler`
- Handler: `lambda_function.lambda_handler`
- Runtime: Python 3.11
- Timeout: 60 seconds
- Memory: 512 MB minimum
- Environment variables:
  - `ENVIRONMENT=production`
  - `DEV_BYPASS_AUTH=false`
  - `DB_SECRET_ARN=algo/database`

**Orchestrator Lambda:**
- Function name: `algo-orchestrator`
- Handler: `lambda_function.lambda_handler`
- Runtime: Python 3.11
- Timeout: 900 seconds (15 minutes)
- Memory: 1024 MB
- Environment variables:
  - `ENVIRONMENT=production`
  - `ORCHESTRATOR_EXECUTION_MODE=auto`
  - `LOG_LEVEL=INFO`

### 3. Configure EventBridge Trigger

Schedule: `cron(0 16 * * ? *)` (4:00 PM ET daily)

### 4. Verify Database Secret

RDS Proxy via `algo/database` secret in Secrets Manager

### 5. Smoke Tests (Post-Deployment)

```bash
curl -H "Authorization: Bearer <token>" https://api.domain.com/api/health
aws lambda invoke --function-name algo-orchestrator --payload '{}' response.json
```

## Verification Results

✅ System is production-ready
✅ All critical components verified
✅ No blockers to AWS deployment
