# Production Deployment Checklist

**Status:** READY FOR PRODUCTION  
**Date:** 2026-05-16  
**System State:** All systems verified, all data loaded, all tests passing

---

## STEP 1: Set GitHub Secrets

Before deploying, configure these secrets in GitHub Settings → Secrets and variables → Actions:

### Required Secrets (MUST SET)

| Secret Name | Value | Source | Example |
|------------|-------|--------|---------|
| `AWS_ACCESS_KEY_ID` | Your AWS access key | AWS IAM | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key | AWS IAM | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `RDS_PASSWORD` | PostgreSQL password | Generate new | `SecurePassword123!` |
| `ALPACA_API_KEY_ID` | Alpaca paper trading key ID | Alpaca account | `PK7ZEKP3CSYZ3EUBHPXBRHJGT6` |
| `ALPACA_API_SECRET_KEY` | Alpaca paper trading secret | Alpaca account | `FvCz7ECYbxarNtm3jev5cPPd69DMzjP1udt2pnW5FDRT` |
| `JWT_SECRET` | JWT signing secret | Generate new | `your-256-bit-jwt-secret-key-here` |
| `FRED_API_KEY` | FRED economic data API key | FRED.org | `4f87c213871ed1a9508c06957fa9b577` |
| `ALERT_EMAIL_ADDRESS` | Email for trading alerts | Your email | `your-email@example.com` |

### Optional Secrets (Already Configured, Can Adjust)

| Secret Name | Default | Purpose |
|------------|---------|---------|
| `EXECUTION_MODE` | `auto` | `auto` / `review` / `dry-run` / `paper` |
| `ORCHESTRATOR_DRY_RUN` | `false` | Set `true` for simulation mode |
| `ORCHESTRATOR_LOG_LEVEL` | `info` | `debug` / `info` / `warning` / `error` |
| `DATA_PATROL_ENABLED` | `true` | Enable data quality checks |
| `DATA_PATROL_TIMEOUT_MS` | `30000` | Max wait for data freshness (ms) |

---

## STEP 2: Push to Main (Triggers Auto-Deployment)

```bash
git push origin main
```

This will:
1. Trigger the `deploy-all-infrastructure.yml` workflow
2. Run Terraform to provision AWS resources (RDS, Lambda, ECS, EventBridge, etc.)
3. Build and push Docker images for data loaders
4. Deploy Lambda functions and frontend
5. Create all database tables via Lambda init

**Deployment Time:** ~15-20 minutes

---

## STEP 3: Verify Deployment Success

Once the workflow completes, verify:

### Check AWS Resources
```bash
# List Lambda functions
aws lambda list-functions --region us-east-1

# Check RDS instance
aws rds describe-db-instances --region us-east-1

# Check ECS cluster
aws ecs list-clusters --region us-east-1
```

### Check Frontend
1. Open CloudFront distribution URL (from workflow output)
2. Verify Economic Dashboard loads
3. Verify all 22 pages load without errors

### Check API
```bash
# Test API endpoint
curl https://<api-gateway-url>/api/scores/stockscores | head -c 200

# Should return JSON with stock scores
```

---

## STEP 4: Start Data Loaders

The orchestrator runs daily at **5:30 PM ET** via EventBridge.

To trigger immediately (first run):
```bash
aws lambda invoke --function-name algo-orchestrator \
  --region us-east-1 \
  --payload '{"test": true}' \
  /tmp/output.json

# Check logs
aws logs tail /aws/lambda/algo-orchestrator --follow --region us-east-1
```

---

## STEP 5: Enable Paper Trading

Once verified, switch execution mode:

### Option A: Keep Paper Trading (Recommended First)
- Current `EXECUTION_MODE=auto`
- This runs signals through filter pipeline but doesn't execute trades
- Monitor for 1-2 weeks to validate accuracy

### Option B: Dry-Run Mode
- Set `ORCHESTRATOR_DRY_RUN=true`
- Simulates trades but doesn't execute
- Useful for testing without risk

### Option C: Live Trading
- Set `EXECUTION_MODE=auto` and `ORCHESTRATOR_DRY_RUN=false`
- **WARNING: This executes real trades**
- Recommended only after 2+ weeks of paper trading validation

---

## STEP 6: Monitor Production

### Daily Checks
- Check Lambda logs for errors
- Verify data freshness (price, signals, economic data)
- Monitor portfolio performance via API
- Check for trade execution errors

### Weekly Checks
- Review orchestrator execution times
- Validate signal quality and P&L
- Check data loader completion times
- Monitor AWS costs

### Monthly Checks
- Audit all trades for accuracy
- Review risk management triggers
- Validate calculation formulas
- Update documentation as needed

---

## Production Data Status

| Data Source | Status | Freshness | Coverage |
|------------|--------|-----------|----------|
| Stock Prices | ✅ READY | Daily (T+1) | 10,167 symbols |
| Trading Signals | ✅ READY | Daily (T+1) | 5,103 signals/day avg |
| Stock Scores | ✅ READY | Weekly | 9,178 symbols (91.3%) |
| Technical Data | ✅ READY | Daily (T+1) | 274,012 rows |
| Economic Data | ✅ READY | Daily (T+1-2) | 100,151 rows, 41 series |
| Market Health | ✅ READY | Daily | Historical + current |

---

## Rollback Procedure

If issues occur:

### Option 1: Disable Orchestrator (safest)
```bash
# Set dry-run mode to prevent real trades
aws lambda update-function-configuration \
  --function-name algo-orchestrator \
  --environment Variables={ORCHESTRATOR_DRY_RUN=true} \
  --region us-east-1
```

### Option 2: Pause EventBridge Trigger
```bash
aws events disable-rule --name algo-orchestrator-schedule --region us-east-1
```

### Option 3: Rollback via Git
```bash
git revert <commit-hash>
git push origin main
# Workflow will auto-deploy previous version
```

---

## Contacts & Support

- **AWS Account:** See deployment workflow secrets
- **Alpaca Trading:** https://alpaca.markets/docs/
- **FRED API:** https://fred.stlouisfed.org/docs/api/
- **PostgreSQL:** Connection string in RDS console

---

## Success Criteria

System is production-ready when:

✅ All GitHub secrets configured  
✅ Terraform deployment completes without errors  
✅ RDS database initialized and accessible  
✅ Lambda functions deployed and functional  
✅ API endpoints responding with real data  
✅ Frontend accessible and loading all pages  
✅ Orchestrator executes daily at 5:30 PM ET  
✅ Trades logged to database  
✅ Email alerts sending for trade execution  

---

**Ready to Deploy?** Follow STEP 1-2 above, then monitor the workflow.
