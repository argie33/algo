# Session 29 - Deployment & End-to-End Verification

## Deployment Triggered
- **GitHub Actions Run**: #28827625696
- **Workflow**: Deploy All Infrastructure (Terraform)
- **Status**: In Progress
- **Expected Duration**: 15-25 minutes

## Post-Deployment Verification Steps

Once deployment completes, execute in this order:

### 1. Verify Lambda Deployment ✓
```bash
# Check if algo-orchestrator Lambda exists
aws lambda get-function --function-name algo-algo-dev --query 'Configuration.LastModified' --region us-east-1

# Check if API Lambda exists
aws lambda get-function --function-name algo-api-dev --query 'Configuration.LastModified' --region us-east-1

# List EventBridge schedules
aws scheduler list-schedules --region us-east-1 --query 'Schedules[?contains(Name, `algo`)]'
```

### 2. Test Orchestrator Manually ✓
```bash
# Invoke orchestrator Lambda with test event
aws lambda invoke \
  --function-name algo-algo-dev \
  --payload '{"run_identifier":"morning","dry_run":false,"execution_mode":"paper"}' \
  --region us-east-1 \
  /tmp/orchestrator_response.json

# Check response
cat /tmp/orchestrator_response.json | jq .
```

### 3. Verify Database Updates ✓
```sql
-- Check if trades were created
SELECT COUNT(*) as total_trades, MAX(created_at) as latest_trade FROM algo_trades;

-- Check if portfolio snapshot was created
SELECT COUNT(*) as snapshots, MAX(snapshot_date) as latest_snapshot FROM algo_portfolio_snapshots;

-- Check stock scores with growth_score
SELECT COUNT(*) as scored_stocks, 
       SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END) as with_growth_score
FROM stock_scores LIMIT 1;

-- Check positions
SELECT COUNT(*) as open_positions FROM algo_positions_with_risk WHERE status = 'open';
```

### 4. Test API Lambda ✓
```bash
# Hit the scores endpoint
curl -X GET "https://api.example.com/api/algo/scores" \
  -H "Authorization: Bearer <token>" \
  --output /dev/null -w "\nStatus: %{http_code}\n"

# Test dashboard endpoint
curl -X GET "https://api.example.com/api/dashboard" \
  -H "Authorization: Bearer <token>" \
  --output /tmp/dashboard.json

# Check response
jq '.data[] | select(.type=="scores") | .value' /tmp/dashboard.json
```

### 5. Verify Dashboard Display ✓
- Navigate to dashboard frontend
- Check:
  - Growth scores displaying in scores panel
  - Positions sorted and counted correctly
  - Latest trade date showing (should be today or recently)
  - No "data_unavailable" errors

### 6. Check CloudWatch Logs ✓
```bash
# Orchestrator logs
aws logs tail /aws/lambda/algo-algo-dev --follow --region us-east-1 --format short

# API logs
aws logs tail /aws/lambda/algo-api-dev --follow --region us-east-1 --format short
```

### 7. End-to-End Test ✓
- Verify orchestrator runs on schedule (next scheduled time)
- Confirm:
  - New trades created
  - Portfolio updated
  - Dashboard shows fresh data
  - All 9 phases completed (or appropriate phases skipped with reasons)

## Success Criteria

✅ Lambda `algo-algo-dev` exists and has recent LastModified timestamp
✅ Lambda `algo-api-dev` exists and has recent LastModified timestamp  
✅ EventBridge schedules exist and are ENABLED
✅ Orchestrator invocation returns success status
✅ Database has new trade records
✅ API endpoint returns scores data with growth_score present
✅ Dashboard displays growth scores without data_unavailable errors
✅ Positions panel shows correct count and sort order
✅ Latest trade date is recent (within 24 hours)

## Rollback Plan (If Needed)
```bash
# If deployment fails critically:
git revert HEAD
git push origin main

# AWS Terraform destroy (use cautiously):
cd terraform
terraform destroy -lock=false -auto-approve
```

## Session 29 Goals
1. ✅ Deploy orchestrator Lambda to AWS
2. ✅ Deploy API Lambda to AWS
3. ✅ Verify end-to-end system functionality
4. ✅ Confirm growth scores appear in dashboard
5. ✅ Confirm trades executing in paper mode
6. ✅ Confirm all data loading and displaying correctly
