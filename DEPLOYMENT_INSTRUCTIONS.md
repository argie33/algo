# Deployment Instructions for Data Loader Fix

## Status
- ✅ Bug identified and fixed in code
- ✅ Fix committed to git main (commit 6f3f377ee)
- ⏳ **PENDING**: Deploy to AWS to activate fix
- ⏳ **PENDING**: Loaders run to refresh stale data

## What's Fixed
**Critical bug**: Watermark manager couldn't parse fiscal_year integers, causing quarterly loaders to fail

**Impact when deployed**:
- quarterly_income_statement: Will fetch and load new quarterly data
- quarterly_cash_flow: Will fetch and load new quarterly data
- Dashboard: Data will update from 2026-06-22 stale → 2026-06-29 current

## Deployment Steps (for admin user)

### Option 1: Terraform Deployment (Recommended)
```bash
cd terraform
terraform apply -auto-approve

# Expected output: Updates ECS task definitions for quarterly loaders
# Time: ~5 minutes
```

### Option 2: Manual AWS Console (If Terraform unavailable)
1. Go to AWS ECS Console → Task Definitions
2. Find: `algo-financials_quarterly_income-loader`
3. Click "Create new revision"
4. Update task definition (no changes needed - just to pick up new code from repo)
5. Repeat for `algo-financials_quarterly_cashflow-loader`
6. Set as default revision

### Option 3: Trigger Loaders Manually (For immediate testing)
```bash
# Trigger quarterly income loader now
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-financials_quarterly_income-loader \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[SUBNET_ID],securityGroups=[SG_ID]}"

# Trigger quarterly cash flow loader now
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-financials_quarterly_cashflow-loader \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[SUBNET_ID],securityGroups=[SG_ID]}"
```

## Verification After Deployment

### Check logs immediately
```bash
# Watch quarterly income loader logs (will complete in ~30-45 min)
aws logs tail /ecs/algo-financials_quarterly_income-loader --follow

# Watch quarterly cash flow loader logs
aws logs tail /ecs/algo-financials_quarterly_cashflow-loader --follow
```

### Expected log output
```
[quarterly_income_statement] Starting load: 10574 symbols (parallelism=1)
AAPL: Fetched 54 quarterly income statement row(s)
...
[quarterly_income_statement] Done. fetched=XXXX inserted=YYYY (processed=10574)
✅ [OK] quarterly_income_statement
```

### Verify data in database
```bash
# Check if new data was inserted (should show 2026 as latest year)
aws rds-data execute-statement \
  --resource-arn arn:aws:rds:us-east-1:626216981288:db:algo-prod \
  --database algo \
  --sql "SELECT MAX(fiscal_year) as latest_year, COUNT(*) as record_count FROM quarterly_income_statement"

# Should show: latest_year=2026 (or 2025 if no new filings), record_count > 5,168
```

### Check dashboard
- Navigate to dashboard
- Check "Health" panel
- Should show quarterly_income_statement and quarterly_cash_flow with current date
- Color should change from red (STALE) to green (CURRENT)

## Rollback (If issues occur)
If deployed and loader fails:
1. Check CloudWatch logs for error message
2. Revert to previous ECS task definition revision
3. Contact engineer to debug

## Timeline After Deployment

| Time | Event |
|------|-------|
| **Now** | Deploy fix to AWS (5 min) |
| **+30 min** | Quarterly loaders complete (60-90 min runtime) |
| **+90 min** | Dashboard data refreshes (automatic) |
| **+2 hours** | Morning orchestrator uses new quarterly data |

## Contact

- **If deployment fails**: Check IAM permissions for algo-admin role
- **If loaders fail**: Check CloudWatch `/ecs/algo-financials_quarterly_*` logs
- **If data doesn't load**: Verify SEC EDGAR API is accessible (occasional outages)

## Code Details
- **File changed**: `utils/watermark_manager.py`
- **Function**: `_parse_watermark_date()`
- **Lines**: 63-83
- **Risk**: Very low (isolated parsing logic)
- **Testing**: Verified locally with quarterly_income_statement and quarterly_cash_flow loaders

## Quick Summary
The bug fix is ready and committed. Just need to deploy to AWS. Once deployed, quarterly data will load automatically on next scheduled run (or immediately if manually triggered).
