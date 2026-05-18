# AWS Loader Fix & Deployment Guide

**Last Updated:** 2026-05-17  
**Goal:** Fix all issues with AWS loaders so we can load complete data and run algo with Friday data  
**Status:** Infrastructure in place, testing tools ready

---

## The Problem

- Loaders are configured in AWS (ECS tasks, EventBridge schedules)  
- Infrastructure deployed successfully  
- BUT: No data has been loaded yet (weekend/testing phase)  
- Need to populate all data tiers for complete algo execution  
- Need to test orchestrator with Friday (May 15) data  
- Need to verify everything works via CloudWatch logs  

---

## The Solution: 3-Step Process

### Step 1: Local Testing (Verify Everything Works Locally First)

```bash
# 1. Load all data locally (all 40 loaders, ~35-40 minutes)
python3 run-all-loaders.py

# 2. Verify data is in database
psql -h localhost -U stocks -d stocks <<EOF
  SELECT COUNT(*) as symbols FROM stock_symbols;
  SELECT COUNT(*) as prices FROM price_daily WHERE date = '2026-05-15';
  SELECT COUNT(*) as signals FROM buy_sell_signal_daily WHERE date = '2026-05-15';
EOF

# 3. Test orchestrator with Friday data
python3 test-with-friday-data.py

# This will:
# - Check if all required data is loaded
# - Run the orchestrator with May 15, 2026 data
# - Show what trades would trigger
# - Record results in algo_audit_log table
```

**Expected Output:**
```
✅ All required data is available
✅ Orchestrator ran successfully
✅ Execution logged in audit table
```

---

### Step 2: Deploy to AWS

Once local testing passes:

```bash
# 1. Push to main (triggers GitHub Actions deployment)
git push origin main

# 2. Watch deployment progress
open https://github.com/argie33/algo/actions

# Expected: All jobs complete successfully
# - Bootstrap Terraform Backend
# - Terraform Apply (infrastructure)
# - Build & Push Docker image
# - Deploy Algo Lambda
# - Deploy API Lambda
# - Deploy Frontend
```

---

### Step 3: Verify AWS is Working

```bash
# 1. Run verification script (checks infrastructure)
python3 verify-loaders-aws.py

# Expected output:
# ✅ AWS Credentials OK
# ✅ ECS Cluster: algo-cluster
# ✅ RDS Host: algo-db.*.us-east-1.rds.amazonaws.com
# ✅ CloudWatch Log Groups: (N groups found)
# ✅ ECR Repository: (URL)
# ✅ API Endpoint: (URL)
# ✅ Task Definitions: (N loaders)

# 2. Trigger a test loader manually (if AWS credentials available)
./trigger-loader-ecs.sh stock_symbols

# 3. Watch CloudWatch logs
aws logs tail /ecs/algo-stock_symbols-loader --follow

# Expected: Loader logs showing successful execution
```

---

## What Each Component Does

### 1. `AWS_LOADER_FIX_STRATEGY.md`
- Defines the problem and solution phases
- Breaks down work into manageable steps
- Lists success criteria

### 2. `verify-loaders-aws.py`
Infrastructure verification tool that checks:
- AWS credentials configured
- ECS cluster exists and is healthy
- RDS database is accessible  
- CloudWatch log groups created
- Docker image in ECR
- API Gateway responding
- ECS task definitions available
- Current database contents

**Usage:**
```bash
python3 verify-loaders-aws.py
```

### 3. `test-with-friday-data.py`
Testing and validation tool that:
- Checks if all required data is loaded
- Runs data loaders if data is missing
- Executes orchestrator with Friday data (May 15, 2026)
- Verifies results in audit logs
- Shows what trades would trigger

**Usage:**
```bash
# Full test (load data if needed, then run orchestrator)
python3 test-with-friday-data.py

# Skip loading, just check if data exists
python3 test-with-friday-data.py --check-only

# Skip loading, just run orchestrator with existing data
python3 test-with-friday-data.py --no-load
```

### 4. `trigger-loader-ecs.sh` (Existing)
Manually triggers a specific loader in AWS ECS:
- Starts the ECS task
- Monitors execution
- Streams CloudWatch logs
- Shows completion status

**Usage:**
```bash
./trigger-loader-ecs.sh stock_symbols     # Load stock symbols
./trigger-loader-ecs.sh stock_prices_daily # Load prices
./trigger-loader-ecs.sh signals_daily      # Generate signals
```

---

## How Data Flows Through AWS

```
┌─────────────────────────────────────────────────────────┐
│ GitHub Actions Workflow (triggered on push to main)     │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ Terraform Apply (creates/updates infrastructure)        │
│ - ECS Cluster                                           │
│ - RDS Database                                          │
│ - Task Definitions for 40 loaders                       │
│ - EventBridge scheduled rules                           │
│ - CloudWatch log groups                                 │
│ - Secrets Manager integration                           │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ Docker Image Built & Pushed to ECR                      │
│ - Python 3.11                                           │
│ - All loader scripts                                    │
│ - Dependencies installed                                │
│ - Entrypoint: runs specific loader based on env var    │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ EventBridge Schedules Trigger (daily 3:30am-1pm ET)    │
│ - 3:30am ET: Stock symbols                              │
│ - 4:00am ET: Daily prices (parallel)                    │
│ - 10:00am ET: Financial statements                      │
│ - 12:00pm ET: Market & economic data                    │
│ - 5:00pm ET: Trading signals                            │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ ECS Tasks Execute Loaders                               │
│ - Fargate: serverless container execution               │
│ - 2 vCPU, 4GB RAM (for CPU-heavy loaders)               │
│ - Credentials from Secrets Manager                      │
│ - Logs to CloudWatch                                    │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ RDS Database (PostgreSQL 14)                            │
│ - Receives data from loaders                            │
│ - 121 tables with comprehensive schema                  │
│ - 5000+ stocks, ETFs, market data                       │
│ - 6 months of daily prices                              │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ API Gateway + Lambda (Python 3.11)                      │
│ - REST endpoints for frontend                           │
│ - Queries RDS for real data                             │
│ - Returns JSON responses                                │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ CloudFront CDN                                          │
│ - Serves React frontend                                 │
│ - Caches static assets                                  │
│ - Proxies API calls to API Gateway                      │
└─────────────────────────────────────────────────────────┘
```

---

## Verification Checklist

Use this checklist to verify everything is working:

### Local (No AWS credentials needed)
- [ ] Run `python3 test-with-friday-data.py`
  - [ ] Data loads successfully
  - [ ] Orchestrator completes 7 phases
  - [ ] Results show in audit logs
  - [ ] Trades recorded if signals trigger

### AWS (AWS credentials required)
- [ ] Run `python3 verify-loaders-aws.py`
  - [ ] All infrastructure checks pass
  - [ ] Database shows loaded data
- [ ] Run `./trigger-loader-ecs.sh stock_symbols`
  - [ ] Task starts successfully
  - [ ] CloudWatch logs show execution
  - [ ] Completes with exit code 0
- [ ] Check API endpoint:
  ```bash
  API=$(aws apigatewayv2 get-apis --region us-east-1 \
    --query 'Items[0].ApiEndpoint' --output text)
  curl "$API/health"
  # Expected: {"status": "healthy"}
  ```

### Data Quality
- [ ] Database has stock symbols (10,000+)
- [ ] Database has Friday prices (for 5/15/2026)
- [ ] Database has buy/sell signals (for 5/15/2026)
- [ ] CloudWatch logs show "success" for each loader

---

## Troubleshooting

### Issue: `python3 test-with-friday-data.py` fails with "No database connection"
**Solution:** Make sure PostgreSQL is running and credentials are set:
```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=<password>
```

### Issue: Loaders time out in AWS
**Solution:** Some loaders (prices, signals) are heavy and need time:
- stock_prices_daily: up to 30 minutes for 5000+ stocks
- loadstockscores.py: up to 20 minutes for calculation
- This is expected and configured in Terraform (cpu/memory/timeout)

### Issue: CloudWatch logs show "DB connection refused"
**Solution:** Loaders in ECS need network access to RDS:
- Check VPC security groups allow inbound on port 5432
- Check RDS endpoint is reachable from ECS private subnet
- Use: `aws ec2 describe-security-groups --filters "Name=group-name,Values=algo-rds"`

### Issue: "APCA_API_KEY_ID not found" in logs
**Solution:** Secrets Manager not integrated properly:
- Check: `aws secretsmanager describe-secret --secret-id algo-algo-secrets-dev`
- Verify ECS task execution role has permission to read secrets
- See: `terraform/modules/iam/main.tf`

---

## How to Run Full Data Pipeline

### All at once (local)
```bash
python3 run-all-loaders.py
# Runs 40 loaders across 10 dependency tiers
# ~35-40 minutes total
# Shows progress in real-time
```

### Tier by tier (AWS with manual control)
```bash
# Tier 0: Symbols
./trigger-loader-ecs.sh stock_symbols
aws logs tail /ecs/algo-stock-symbols-loader --follow

# Wait for completion, then Tier 1: Prices
./trigger-loader-ecs.sh stock_prices_daily
./trigger-loader-ecs.sh etf_prices_daily
aws logs tail /ecs/algo-* --follow

# Continue with other tiers...
```

---

## Success Criteria

✅ All 40 loaders execute without errors  
✅ RDS database populated with data for May 15, 2026  
✅ CloudWatch logs show execution success  
✅ Orchestrator runs with Friday data  
✅ Audit logs recorded in database  
✅ Trades trigger correctly if buy signals present  
✅ Frontend receives real data from API  

---

## Files Involved

| File | Purpose |
|------|---------|
| `run-all-loaders.py` | Orchestrate local loader execution |
| `test-with-friday-data.py` | Test orchestrator with Friday data |
| `verify-loaders-aws.py` | Verify AWS infrastructure |
| `trigger-loader-ecs.sh` | Manually trigger loaders in AWS |
| `terraform/modules/loaders/main.tf` | ECS task definitions & schedules |
| `Dockerfile` | Docker image for loaders |
| `entrypoint.sh` | Container startup script |
| `loaders/*.py` | 40 individual loader scripts |
| `algo/algo_orchestrator.py` | Trading algorithm execution |
| `.github/workflows/deploy-all-infrastructure.yml` | AWS deployment automation |

---

## Next Steps

1. **Test locally:**
   ```bash
   python3 test-with-friday-data.py
   ```

2. **If passing, deploy to AWS:**
   ```bash
   git push origin main
   # Wait for GitHub Actions to complete
   ```

3. **Verify AWS is working:**
   ```bash
   python3 verify-loaders-aws.py
   ```

4. **Trigger test loader (if AWS credentials available):**
   ```bash
   ./trigger-loader-ecs.sh stock_symbols
   aws logs tail /ecs/algo-stock_symbols-loader --follow
   ```

5. **Check results:**
   - CloudWatch logs show "success"
   - Database populated with data
   - API endpoint responding
   - Frontend showing real data

---

**Total Time to Full Operational Status:**
- Local testing: 40-50 minutes (loaders)
- AWS deployment: 10-15 minutes (GitHub Actions)
- Verification: 5-10 minutes (manual checks)
- **Total: ~60-75 minutes**

---

## Questions?

Check the detailed files:
- Strategy: `AWS_LOADER_FIX_STRATEGY.md`
- Architecture: `algo-tech-stack.md`
- Deployment: `DEPLOYMENT_GUIDE.md`
- Troubleshooting: `troubleshooting-guide.md`
- Status: `STATUS.md`
