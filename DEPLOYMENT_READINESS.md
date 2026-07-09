# Deployment Readiness Checklist

**Status:** READY FOR AWS DEPLOYMENT (Code Complete - Infrastructure Pending)

## Prerequisites

- [ ] GitHub repository with workflow permissions
- [ ] AWS Account with admin access (for Terraform apply)
- [ ] Alpaca API credentials (paper trading account)

## System Components - Status

| Component | Status | Deploy Method |
|-----------|--------|----------------|
| Orchestrator Lambda | ✓ Code Ready | GitHub Actions + Terraform |
| API Lambda | ✓ Code Ready | GitHub Actions + Terraform |
| RDS Database | ✓ Configured | Terraform (auto-created) |
| DynamoDB Tables | ✓ Configured | Terraform (auto-created) |
| S3 Buckets | ✓ Configured | Terraform (auto-created) |
| EventBridge Scheduler | ✓ Configured | Terraform (2x daily trigger) |
| ECS Loaders | ✓ Configured | Docker + Terraform |
| CloudFront Distribution | ✓ Configured | Terraform |
| VPC/Network | ✓ Configured | Terraform |

## Deployment Steps

### 1. Deploy Infrastructure (AWS Admin Required)

**Local deployment (if you have admin credentials):**
```bash
cd terraform
terraform apply -lock=false
```

**OR via GitHub Actions (Recommended):**
```bash
# Push code to GitHub main branch
git push origin main

# Go to Actions tab in GitHub
# Click "Deploy All Infrastructure (Terraform)"
# Click "Run workflow" with default settings
# Wait for deployment to complete (~10-15 minutes)
```

**Verify deployment:**
```bash
# Check CloudFormation stacks
aws cloudformation list-stacks --region us-east-1

# Check RDS instance
aws rds describe-db-instances --region us-east-1

# Check Lambda functions
aws lambda list-functions --region us-east-1
```

### 2. Verify Orchestrator Execution

**Check EventBridge Schedule:**
```bash
aws scheduler list-schedules --region us-east-1
```

**Manually trigger orchestrator (testing):**
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

**Check orchestrator logs:**
```bash
aws logs tail /aws/lambda/algo-orchestrator-dev --follow
```

### 3. Start Dashboard (Local or EC2)

**Local development:**
```bash
cd webapp
npm install
npm run dev  # Runs on http://localhost:3000
```

**Verify dashboard connects to API:**
- Open http://localhost:3000
- Check browser console for errors
- Verify /api/portfolio returns data

### 4. Test Alpaca Integration

**Set Alpaca credentials:**
```bash
export ALPACA_API_KEY_ID=<your_paper_key>
export ALPACA_API_SECRET_KEY=<your_paper_secret>
```

**Run Alpaca integration test:**
```bash
python3 test_alpaca_integration.py
```

**Run complete system test:**
```bash
export ORCHESTRATOR_EXECUTION_MODE=paper
python3 test_complete_integration.py
```

### 5. Monitor Production Execution

**Check orchestrator runs (2x daily at 9:30 AM and 1 PM ET):**
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/algo-orchestrator-dev \
  --start-time $(($(date +%s) - 3600))000 \
  --region us-east-1
```

**Check for circuit breaker triggers:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace Algo \
  --metric-name CircuitBreakerTriggered \
  --start-time 2026-07-01T00:00:00Z \
  --end-time 2026-07-31T23:59:59Z \
  --period 86400 \
  --region us-east-1
```

**Monitor portfolio:**
- View dashboard at http://api.example.com (once deployed)
- Check `/api/portfolio` for current holdings
- Check `/api/positions` for open positions
- Check `/api/signals` for pending trades

## Testing Checklist (After Deployment)

### Unit Tests
- [ ] Run orchestrator end-to-end: `export ORCHESTRATOR_EXECUTION_MODE=paper && python3 run_end_to_end_test.py`
- [ ] All 1066 pytest tests pass: `pytest`
- [ ] Type checking passes: `mypy --strict algo/`

### Integration Tests
- [ ] Dashboard API responding: `python3 test_dashboard_integration.py`
- [ ] Alpaca connectivity working: `python3 test_alpaca_integration.py`
- [ ] Complete system test passes: `python3 test_complete_integration.py`

### Live System Tests
- [ ] EventBridge triggers orchestrator on schedule
- [ ] CloudWatch logs show successful executions
- [ ] Dashboard displays portfolio data
- [ ] Positions sync correctly from Alpaca
- [ ] Circuit breakers prevent over-trading

## Rollback Procedure

**If something breaks:**

1. **Stop orchestrator execution:**
   ```bash
   # Disable EventBridge schedule
   aws scheduler update-schedule \
     --name algo-orchestrator-2x-daily-dev \
     --flexible-time-window '{"Mode":"OFF"}' \
     --state DISABLED
   ```

2. **Revert Terraform changes:**
   ```bash
   cd terraform
   git revert HEAD
   terraform apply -lock=false
   ```

3. **Restore from backup:**
   ```bash
   # RDS automated backups available in AWS Console
   # Restore to point-in-time if data corruption
   ```

## Monitoring & Alerts

**Set up CloudWatch alarms:**
- Orchestrator execution failures
- Circuit breaker triggers
- High error rates in Lambdas
- Database connection failures
- API response time > 5 seconds

**Configure SNS notifications:**
```bash
# Already configured in Terraform
# Alerts sent to SNS topic: algo-algo-alerts-dev
```

## Cost Optimization (Already Applied)

- [x] RDS Proxy for connection pooling
- [x] VPC Endpoints for S3/DynamoDB
- [x] CloudWatch Logs retention (30 days)
- [x] Lambda concurrency limits
- [x] DynamoDB on-demand billing
- [x] ECS autoscaling

**Expected monthly cost:** $200-220 (73% reduction from original)

## Support

For deployment issues:
1. Check CloudWatch Logs: `/aws/lambda/algo-*` and `/aws/ecs/*`
2. Verify IAM permissions: User must have AdministratorAccess for Terraform
3. Check Terraform state: `terraform show`
4. Review steering docs: `steering/OPERATIONS.md`

---

**Last Updated:** 2026-07-09
**Next Deployment Target:** Immediate (all code ready)
**Estimated Deploy Time:** 15-20 minutes
**Estimated Testing Time:** 30-45 minutes
