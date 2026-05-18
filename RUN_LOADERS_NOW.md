# Run Loaders Now - Quick Reference

## 🚀 Execute Loaders via GitHub Actions (Recommended)

### Option 1: Run All Loaders (Complete Data Load)
1. Go to: https://github.com/argie33/algo/actions
2. Select **"Manual Trigger Loaders"** workflow (left sidebar)
3. Click **"Run workflow"** button
4. Default is `all` - just click **"Run workflow"**
5. Wait for execution to complete (~90 minutes)

### Option 2: Run Individual Tiers (Testing)
1. Go to: https://github.com/argie33/algo/actions
2. Select **"Manual Trigger Loaders"** workflow
3. Click **"Run workflow"** dropdown
4. Select tier:
   - `tier-0` - Stock symbols (foundation, 5 min)
   - `tier-1-prices` - Price data (15 min)
   - `tier-2-reference` - Company data (30 min)
   - `tier-3-metrics` - Computed metrics (30 min)
   - `all` - Everything (~90 min)
5. Click **"Run workflow"**

---

## 📊 Monitor Execution

### Watch Loaders in Real-Time
```bash
# Replace with your AWS region/account
aws logs tail /ecs/algo-stock_symbols-loader --follow --region us-east-1
```

### Check GitHub Actions Progress
- https://github.com/argie33/algo/actions
- Click latest "Manual Trigger Loaders" run
- See real-time execution in "Trigger Tier 0" (or other selected tier) step

### CloudWatch Logs
- https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logStream:group=/ecs/algo-

---

## ✅ Verify Data Loaded

### After loaders complete:

```bash
# Via API (once complete)
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?limit=1

# Via AWS CLI (direct to RDS)
psql -h <RDS_ENDPOINT> -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols;"
```

Expected results:
- ✓ 5,000+ stock symbols
- ✓ 100,000+ daily prices
- ✓ Prices dated latest Friday (May 17, 2026 or today if today is Friday)
- ✓ Company profiles for 2,000+ symbols

---

## 🎯 Test Orchestrator with Loaded Data

Once loaders complete and data is verified:

```bash
# Manually trigger orchestrator via AWS CLI
aws ecs run-task \
  --cluster algo-dev \
  --task-definition algo-algo-orchestrator \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[SUBNET_ID],securityGroups=[SG_ID],assignPublicIp=DISABLED}" \
  --region us-east-1

# Monitor orchestrator execution
aws logs tail /ecs/algo-algo-orchestrator --follow --region us-east-1
```

---

## 🔧 Troubleshooting

### If workflow fails to start
- Check GitHub Actions secrets are configured in repo settings
- Verify `AWS_ACCOUNT_ID` secret exists
- Ensure AWS IAM role `algo-svc-github-actions-dev` exists

### If loader task doesn't start
```bash
# Check ECS cluster status
aws ecs describe-clusters --clusters algo-dev --region us-east-1

# Check task definition exists
aws ecs list-task-definitions --family-prefix algo-stock_symbols-loader --region us-east-1

# Check RDS is accessible
aws rds describe-db-instances --db-instance-identifier algo-db --region us-east-1
```

### If no data appears after loader completes
- Check CloudWatch logs for error messages
- Verify database credentials in Secrets Manager
- Ensure Alpaca API key is configured (for price data)
- Check if the API providers (yfinance, Finnhub, etc.) are responding

---

## 📋 Expected Timeline

| Tier | Time | What Happens |
|------|------|-------------|
| Tier 0 | 5 min | Load 5,000+ stock symbols |
| Tier 1 | 15 min | Load price history (daily/weekly/monthly) |
| Tier 2 | 30 min | Load company profiles, earnings, metrics |
| Tier 3 | 30 min | Compute growth/quality/value metrics |
| **Total** | **~90 min** | **Complete dataset ready for trading** |

---

## 📌 Key Benefits

✅ **No Monday Wait** - Load Friday data immediately for weekend testing
✅ **Automated** - Workflow handles all orchestration
✅ **Monitored** - Real-time CloudWatch logs during execution
✅ **Resumable** - Run individual tiers for testing
✅ **Production Ready** - Uses same infrastructure as scheduled loaders

---

**Status**: Ready to execute
**Last Updated**: 2026-05-18
**Next Step**: Click "Run workflow" on GitHub Actions
