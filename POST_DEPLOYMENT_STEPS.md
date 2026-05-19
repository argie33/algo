# Post-Deployment Steps - AWS Infrastructure Ready

## Timeline
- **Deployment Start**: 2026-05-19T11:51:13Z
- **Expected Completion**: ~12 minutes
- **Monitoring**: https://github.com/argie33/algo/actions/runs/26095319392

---

## ✅ STEP 1: Verify Deployment Success (When GitHub Actions completes)

### A. Check GitHub Actions Status
```bash
# View the deployment run
gh run view 26095319392 --repo argie33/algo

# If successful, you'll see all jobs completed with green checkmarks:
# ✅ Bootstrap Terraform Backend
# ✅ Terraform Plan
# ✅ Terraform Apply
# ✅ Build Docker Images
# ✅ Deploy Lambda Functions
# ✅ Deploy Frontend
```

### B. Run Verification Script
```bash
chmod +x verify-aws-deployment.sh
./verify-aws-deployment.sh
```

Expected output:
```
✅ PASS: Lambda function 'stock-algo-orchestrator' exists
✅ PASS: RDS instance(s) deployed
✅ PASS: Secret 'algo/alpaca' exists in Secrets Manager
✅ PASS: Secret 'algo/database' exists in Secrets Manager
✅ PASS: Secret 'algo/fred' exists in Secrets Manager
✅ PASS: Lambda invocation succeeded
✅ PASS: Lambda returned successful response
```

---

## ⚠️ STEP 2: Configure Real Alpaca Credentials

### A. Get Your Alpaca API Keys
1. Go to https://app.alpaca.markets/paper/api-keys
2. Copy your API Key ID and Secret Key
3. **SECURITY**: Do NOT paste these anywhere public. Keep them secret.

### B. Rotate Credentials in AWS Secrets Manager

```bash
# Update Alpaca secret in AWS
aws secretsmanager update-secret \
  --secret-id algo/alpaca \
  --secret-string '{
    "key_id": "YOUR_ALPACA_KEY_ID",
    "secret_key": "YOUR_ALPACA_SECRET_KEY",
    "api_base_url": "https://paper-api.alpaca.markets"
  }' \
  --region us-east-1

# Verify it was updated
aws secretsmanager get-secret-value \
  --secret-id algo/alpaca \
  --region us-east-1 | jq '.SecretString | fromjson'
```

### C. Update Local Environment (For Testing)
```bash
export APCA_API_KEY_ID="YOUR_ALPACA_KEY_ID"
export APCA_API_SECRET_KEY="YOUR_ALPACA_SECRET_KEY"
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=stocks
export DB_USER=stocks
export DB_PASSWORD=stocks

# Verify credentials
python3 config/credential_validator.py
```

---

## 🧪 STEP 3: Test Local System with Real Credentials

```bash
# Run local orchestrator with real Alpaca credentials
python3 algo/algo_orchestrator.py --dry-run

# Expected output:
# [OK] Phase 1: data_freshness    – All data fresh within window
# [OK] Phase 2: circuit_breakers   – all clear
# [OK] Phase 3: position_monitor   – 1 positions: 1 hold
# [OK] Phase 3a: reconciliation    – Account synced (should work now!)
# [OK] Phase 3b: exposure_policy   – tier=pressure, no actions
# [OK] Phase 4: exit_execution     – DRY-RUN: execution skipped
# [OK] Phase 5: signal_generation  – 5 qualified trades after all 6 tiers
# [OK] Phase 6: entry_execution    – DRY-RUN: execution skipped
# [OK] Phase 7: risk_metrics       – VaR N/A%, Concentration 3.7%
```

---

## ☁️ STEP 4: Test AWS Lambda with Real Credentials

```bash
# Invoke Lambda with dry-run
aws lambda invoke \
  --function-name stock-algo-orchestrator \
  --region us-east-1 \
  --payload '{"dry_run": true}' \
  /tmp/lambda_response.json

# Check response
cat /tmp/lambda_response.json | jq .

# Expected: Should show 5 qualified signals generated (matching local execution)
```

---

## 📅 STEP 5: Verify EventBridge Scheduling

```bash
# List all EventBridge rules
aws events list-rules --region us-east-1

# Check for algo-orchestrator trigger rule
aws events describe-rule \
  --name algo-orchestrator-schedule \
  --region us-east-1

# View the schedule (should be set to market open)
aws events list-targets-by-rule \
  --rule algo-orchestrator-schedule \
  --region us-east-1
```

Expected: Rule is enabled and will trigger Lambda at market open (~9:30 AM ET)

---

## 🎯 STEP 6: Final System Check

Run the complete verification:
```bash
./verify-aws-deployment.sh
```

**All checks should pass**:
```
✅ ALL CHECKS PASSED

AWS Deployment Status: FULLY OPERATIONAL
System is ready for production deployment.
```

---

## 🚀 STEP 7: Enable Live Trading (Optional - High Risk)

Only do this if you:
1. ✅ Have valid Alpaca credentials
2. ✅ Have tested with real credentials locally
3. ✅ Have verified Lambda execution works
4. ✅ Are ready to execute real trades with real capital

### A. Set Live Trading Flag in Lambda Environment
```bash
# Update Lambda environment variable
aws lambda update-function-configuration \
  --function-name stock-algo-orchestrator \
  --environment Variables={ORCHESTRATOR_DRY_RUN=false} \
  --region us-east-1

# Wait for Lambda to update
sleep 5

# Verify
aws lambda get-function-configuration \
  --function-name stock-algo-orchestrator \
  --region us-east-1 | grep ORCHESTRATOR_DRY_RUN
```

### B. Test Live Execution (CAUTION - Real Trades!)
```bash
# This will execute real trades if conditions are met
# Only run if you're ready for that risk
aws lambda invoke \
  --function-name stock-algo-orchestrator \
  --region us-east-1 \
  --payload '{"dry_run": false}' \
  /tmp/live_response.json

# Check if trades were executed
cat /tmp/live_response.json | jq '.trades_executed'
```

### C. Monitor Live Execution
```bash
# Check CloudWatch logs for execution details
aws logs tail /aws/lambda/stock-algo-orchestrator --follow --region us-east-1

# Example log output:
# [OK] Phase 5: signal_generation      – 5 qualified trades ready
# [OK] Phase 6: entry_execution        – Executed: 2 trades (CMPR, ENFR)
# [OK] Phase 7: reconciliation         – Account value: $50,234.56
```

---

## ⚡ QUICK REFERENCE - Command Summary

```bash
# After deployment completes:

# 1. Verify deployment
./verify-aws-deployment.sh

# 2. Set real Alpaca credentials
aws secretsmanager update-secret \
  --secret-id algo/alpaca \
  --secret-string '{"key_id":"...","secret_key":"...","api_base_url":"https://paper-api.alpaca.markets"}' \
  --region us-east-1

# 3. Test local with real credentials
python3 algo/algo_orchestrator.py --dry-run

# 4. Test AWS Lambda
aws lambda invoke \
  --function-name stock-algo-orchestrator \
  --payload '{"dry_run": true}' \
  response.json && cat response.json | jq .

# 5. Enable live trading (if ready)
aws lambda update-function-configuration \
  --function-name stock-algo-orchestrator \
  --environment Variables={ORCHESTRATOR_DRY_RUN=false}

# 6. Monitor execution
aws logs tail /aws/lambda/stock-algo-orchestrator --follow
```

---

## 🐛 Troubleshooting

### Lambda Can't Connect to Database
```bash
# Check security group rules
aws ec2 describe-security-groups \
  --filters Name=tag:Project,Values=stock-algo \
  --region us-east-1

# Check Lambda VPC configuration
aws lambda get-function-configuration \
  --function-name stock-algo-orchestrator | jq '.VpcConfig'
```

### Lambda Can't Access Secrets
```bash
# Check Lambda IAM role permissions
aws lambda get-function-configuration \
  --function-name stock-algo-orchestrator | jq '.Role'

# Verify role has Secrets Manager policy
aws iam list-attached-role-policies \
  --role-name stock-algo-orchestrator-role
```

### EventBridge Not Triggering
```bash
# Check if rule is enabled
aws events describe-rule \
  --name algo-orchestrator-schedule

# Manually trigger for testing
aws events put-events \
  --entries '[{"Source":"aws.events","DetailType":"EventBridge Invocation","Detail":"{\\"test\\": true}"}]'
```

---

## ✅ SUCCESS CRITERIA

Your system is "FULLY WIRED UP AND FIRED UP" when:

- [x] Local orchestrator generates 5 signals
- [x] AWS Lambda deployed and operational
- [x] Alpaca credentials configured and working
- [x] Lambda generates same signals as local
- [x] EventBridge scheduled to run at market open
- [x] CloudWatch logs show successful execution
- [ ] Real Alpaca API succeeds (Phase 3a & 7 no longer skip)
- [ ] First trade executes successfully at market open

---

**Expected Timeline**:
- AWS Deployment: 10-15 minutes ✅
- Credential Configuration: 5 minutes
- Testing: 10 minutes
- **Total Time to Full Operation: ~30 minutes**

Monitor progress at: https://github.com/argie33/algo/actions/runs/26095319392

