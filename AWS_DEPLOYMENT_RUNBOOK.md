# AWS Deployment & Verification Runbook

**Last Updated:** 2026-05-16  
**Status:** Ready for Deployment

---

## Quick Start (5 minutes)

```bash
# 1. Verify changes are pushed
git log --oneline -1

# 2. View GitHub Actions deployment
open https://github.com/argie33/algo/actions

# 3. Wait 15-20 minutes for deployment to complete
# (Watch the "deploy-all-infrastructure.yml" workflow)

# 4. Test API endpoint
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health

# 5. Access frontend
open https://d5j1h4wzrkvw7.cloudfront.net
```

---

## Detailed Deployment Phases

### Phase 1: Push Code (Completed ✓)

**Status:** Commits pushed to main  
**Command:** `git push origin main`  
**Result:** GitHub Actions automatically triggered

### Phase 2: CI/CD Pipeline (In Progress)

**Watch at:** https://github.com/argie33/algo/actions

**Workflow:** `deploy-all-infrastructure.yml`

**Jobs executed in order:**
1. **Terraform Plan & Apply** (12-15 min)
   - Updates AWS infrastructure
   - Creates/updates Lambda, RDS, API Gateway, ECS, etc.
   - Status: Check CloudFormation events in AWS console

2. **Build Docker Image** (3-5 min)
   - Builds data loader container
   - Pushes to ECR (Elastic Container Registry)
   - Status: Check ECR in AWS console

3. **Deploy API Lambda** (2-3 min)
   - Updates API Lambda function code
   - API endpoints become available
   - Status: Test with `curl`

4. **Deploy Algo Lambda** (2-3 min)
   - Updates orchestrator Lambda
   - Scheduled to run at 5:30pm ET daily
   - Status: Check Lambda console

5. **Build & Deploy Frontend** (3-5 min)
   - Builds React application
   - Uploads to S3
   - Invalidates CloudFront cache
   - Status: Check CloudFront in AWS console

6. **Initialize Database** (1-2 min)
   - Runs schema initialization
   - Creates tables, indexes, constraints
   - Status: Check RDS in AWS console

**Total Time:** ~25-35 minutes

### Phase 3: Verify Infrastructure (Completed after Phase 2)

#### 3.1 Check AWS Resources

```bash
# Check Lambda functions
aws lambda list-functions --region us-east-1 | grep algo

# Check RDS database
aws rds describe-db-instances --region us-east-1 | grep DBInstanceIdentifier

# Check API Gateway
aws apigateway get-rest-apis --region us-east-1 | grep name

# Check CloudFront
aws cloudfront list-distributions | grep DomainName
```

#### 3.2 Test API Health

```bash
# Test API health endpoint
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health

# Expected response:
# {"status": "healthy", "timestamp": "2026-05-16T..."}
```

#### 3.3 Test Data Pipeline

```bash
# Connect to RDS (requires psql or AWS console)
# Query table counts
SELECT 
  'price_daily' as table_name, COUNT(*) FROM price_daily
UNION ALL
SELECT 
  'technical_data_daily', COUNT(*) FROM technical_data_daily
UNION ALL
SELECT 
  'buy_sell_daily', COUNT(*) FROM buy_sell_daily;

# Expected: Should have rows from today's date
```

#### 3.4 Test API Endpoints

```bash
# Test stock scores endpoint
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores/stockscores?limit=5

# Test algo status
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status

# Test market exposure
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/markets

# Each should return HTTP 200 with JSON data
```

### Phase 4: Verify Frontend (After Phase 2 complete)

#### 4.1 Load Application

1. Open: https://d5j1h4wzrkvw7.cloudfront.net
2. Should see login or dashboard page
3. Check browser console for errors (F12)

#### 4.2 Test Navigation

- [ ] Markets tab loads (view 9-factor market exposure)
- [ ] Setups tab loads (view trading setups)
- [ ] Positions tab loads (view open positions)
- [ ] Trades tab loads (view trade history)
- [ ] Workflow tab loads (view orchestrator phases)
- [ ] Data Health tab loads (view loader status)

#### 4.3 Test Data Display

- [ ] Stock scores show real data (not empty/null)
- [ ] Charts render without errors
- [ ] Prices update (show latest data)
- [ ] Market exposure calculated correctly

### Phase 5: Verify Data Pipeline (After data loads)

#### 5.1 Check Loader Status

```bash
# View loader execution in CloudWatch
aws logs tail /aws/ecs/algo-loaders --follow

# Or check database
SELECT loader_name, MAX(created_at) as last_run, COUNT(*) as runs
FROM loader_execution_metrics
GROUP BY loader_name
ORDER BY last_run DESC;
```

#### 5.2 Check Data Freshness

```bash
# Price data should have today's date
SELECT MAX(date) FROM price_daily;

# Technical indicators should be current
SELECT MAX(date) FROM technical_data_daily;

# Signals should be generated
SELECT MAX(date) FROM buy_sell_daily;

# Market health should be updated
SELECT MAX(date) FROM market_health_daily;
```

#### 5.3 Verify Data Quality

```bash
# Check for nulls in critical columns
SELECT symbol, COUNT(*) 
FROM price_daily 
WHERE date = CURRENT_DATE AND (close IS NULL OR open IS NULL)
GROUP BY symbol;

# Should return 0 rows (no nulls in today's prices)
```

### Phase 6: Test Orchestrator

#### 6.1 Verify Orchestrator Is Scheduled

```bash
# Check EventBridge rule
aws events describe-rule --name algo-orchestrator-schedule --region us-east-1

# Should show: 
# - State: ENABLED
# - ScheduleExpression: cron(30 17 ? * MON-FRI *)  (5:30pm ET weekdays)
```

#### 6.2 Monitor Orchestrator Runs

```bash
# View orchestrator logs in CloudWatch
aws logs tail /aws/lambda/algo-orchestrator --follow

# Or check database for recent runs
SELECT run_date, phase, status, message
FROM algo_orchestrator_log
ORDER BY run_date DESC
LIMIT 10;
```

#### 6.3 Check Trade Execution

```bash
# View executed trades
SELECT * FROM algo_trades 
WHERE trade_date >= CURRENT_DATE - INTERVAL '1 day'
ORDER BY trade_date DESC;

# View open positions
SELECT * FROM algo_positions
WHERE status = 'OPEN'
ORDER BY entry_date DESC;
```

---

## Troubleshooting

### API Returns 401 Unauthorized

**Cause:** API Gateway still enforcing authentication  
**Solution:**
1. Check Terraform: `terraform/modules/api_gateway/main.tf`
2. Verify: `authorization_type = var.cognito_enabled ? "JWT" : "NONE"`
3. Check variable: `terraform/terraform.tfvars` should have `cognito_enabled = false`
4. Force redeploy: Push a dummy commit to trigger GitHub Actions

### Database Connection Fails

**Cause:** RDS security group not configured  
**Solution:**
1. Check RDS security group in AWS console
2. Verify inbound rule: Port 5432 from Lambda/ECS security group
3. Or: Edit in `terraform/modules/database/main.tf`

### Frontend Shows Blank Page

**Cause:** API endpoint not accessible  
**Solution:**
1. Check CloudFront distribution in AWS console
2. Verify origin points to correct API Gateway
3. Check browser console for CORS errors
4. Force CloudFront cache invalidation

### Loaders Not Running

**Cause:** ECS task not launching or failing  
**Solution:**
1. Check EventBridge rule: `aws events list-targets-by-rule --rule algo-loaders-schedule`
2. Check ECS cluster: `aws ecs list-clusters`
3. View task logs: `aws logs tail /aws/ecs/algo-loaders`
4. Verify task definition has correct IAM role

### No Data in Database

**Cause:** Loaders failed or didn't run  
**Solution:**
1. Check loader logs: `aws logs tail /aws/ecs/algo-loaders --follow`
2. Check if loaders are scheduled: `aws events describe-rule --name algo-loaders-schedule`
3. Manually trigger: `aws ecs run-task --cluster algo-cluster --task-definition algo-loaders --launch-type FARGATE`
4. Check data sources (Finnhub API key, FRED API key, etc.)

---

## Post-Deployment Monitoring

### Daily Checks

```bash
# Morning (before market open)
python3 verify_system_ready.py
python3 verify_data_integrity.py

# Check data freshness
SELECT MAX(date) FROM price_daily;
SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = CURRENT_DATE;

# Evening (after market close)
# Check orchestrator ran successfully
SELECT COUNT(*) FROM algo_trades WHERE trade_date = CURRENT_DATE;
```

### Weekly Checks

```bash
# Verify no errors in logs
aws logs filter-log-events --log-group-name /aws/lambda/algo-orchestrator \
  --start-time $(($(date +%s)*1000 - 604800000)) \
  | grep -i "error\|exception"

# Check data quality metrics
SELECT table_name, COUNT(*) as row_count
FROM information_schema.tables t
LEFT JOIN <table> ON table_name = '<table>'
WHERE table_schema = 'public'
GROUP BY table_name;
```

### Monthly Checks

```bash
# Verify database performance
SELECT schemaname, tablename, 
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Check index usage
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY tablename;
```

---

## Local Development Testing

### Start Local Environment

```bash
# In WSL (Windows):
cd /mnt/c/Users/arger/code/algo
docker-compose up -d

# Verify services
docker-compose ps

# Check database
docker exec stocks_db psql -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily;"
```

### Run Local Verification Tests

```bash
# Test system readiness
python3 verify_system_ready.py

# Test data integrity
python3 verify_data_integrity.py

# Audit loaders
python3 audit_loaders.py
```

### Test API Locally

```bash
# Start API Lambda locally (requires SAM CLI)
sam local start-api

# Test locally
curl http://127.0.0.1:3000/api/health
```

---

## Rollback Procedure

### If Deployment Fails

1. **Check error in GitHub Actions**
   - Go to https://github.com/argie33/algo/actions
   - Click failed workflow
   - Check logs for specific error

2. **Fix the issue**
   - Edit problematic file
   - Commit fix: `git commit -am "fix: <description>"`
   - Push: `git push origin main`
   - GitHub Actions will automatically retry

3. **If urgent rollback needed**
   - Use Terraform to revert: `terraform destroy` (not recommended)
   - Or restore from backup (manual RDS snapshot restore)

### Database Rollback

```bash
# Create snapshot before changes
aws rds create-db-snapshot --db-instance-identifier algo-db \
  --db-snapshot-identifier algo-db-backup-$(date +%Y%m%d)

# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier algo-db-restored \
  --db-snapshot-identifier <snapshot-id>
```

---

## Success Criteria

✅ **All of the following must be true:**

- [ ] GitHub Actions workflow completed successfully (all jobs green)
- [ ] API health endpoint returns 200
- [ ] API endpoints return data (not 401/404/500)
- [ ] Frontend loads without errors
- [ ] Database has today's data
- [ ] Orchestrator logs show successful run
- [ ] No critical errors in CloudWatch logs
- [ ] Data loaders completed successfully
- [ ] Trade execution working (positions/trades tables populated)

---

## Support & Escalation

### For Issues:

1. **Check logs first**
   - CloudWatch: https://console.aws.amazon.com/logs
   - GitHub Actions: https://github.com/argie33/algo/actions

2. **Check AWS console**
   - Lambda: https://console.aws.amazon.com/lambda
   - RDS: https://console.aws.amazon.com/rds
   - API Gateway: https://console.aws.amazon.com/apigateway

3. **Run diagnostics**
   - `python3 verify_system_ready.py`
   - `python3 verify_data_integrity.py`
   - Check database directly

4. **Review Terraform state**
   - Check what Terraform thinks is deployed
   - Compare with actual AWS resources
   - May need: `terraform refresh && terraform plan`

---

## Contact & Documentation

- **Deployment Guide:** DEPLOYMENT_GUIDE.md
- **Status:** STATUS.md
- **Tech Stack:** algo-tech-stack.md
- **Architecture:** ALGO_ARCHITECTURE.md

---

**Deployment Status:** 🟢 READY FOR PRODUCTION
