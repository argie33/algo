# Session 155 Deployment Verification Checklist

## Pre-Deployment Status ✅

- [x] Local system verified working (84.16% growth scores)
- [x] Code fixes verified locally:
  - [x] yfinance_derived_metrics schema fix (commit 47fdbc618)
  - [x] DynamoDB table name attribute fix (commit 0efa2fbf7)
- [x] Orchestrator runs successfully locally
- [x] Database connectivity verified
- [x] Growth metrics calculations correct

## Deployment In Progress ⏳

**Workflow ID:** 29417118841
**Triggered:** 2026-07-15 ~13:00 UTC
**Expected Completion:** ~13:15 UTC

### Expected Deployment Steps

1. Bootstrap Terraform Backend (S3 state + DynamoDB lock)
2. Build Lambda layers (psycopg2, numpy, scipy)
3. Build Lambda function packages (23 total)
4. Terraform validate (SHOULD PASS now with name fix)
5. Terraform apply (create DynamoDB tables)
6. Docker image build/push (ECS loaders)
7. Lambda deployments
8. Frontend deployment (if changes)
9. Database migrations (if any)

## Post-Deployment Verification ✅ When Complete

### 1. Infrastructure Verification

```bash
# Verify DynamoDB tables exist with correct attributes
python3 scripts/verify_session_155_deployment.py
```

Expected output:
```
✓ EXISTS: algo-orchestrator-locks-dev
✓ EXISTS: algo-loader-locks-dev
✓ EXISTS: algo-loader-config-dev
✓ EXISTS: algo-loader-status-dev
✓ EXISTS: algo_orchestrator_state
✓ EXISTS: algo_phase1_cache
✓ EXISTS: algo-contact-rate-limit-dev
✓ EXISTS: algo-token-blocklist-dev
```

### 2. Lambda Orchestrator Test

```bash
# Trigger a test orchestrator run
python3 scripts/trigger_orchestrator.py --run morning --mode paper

# Monitor for completion (should take 3-5 minutes)
python3 scripts/monitor_data_staleness.py --watch 30
```

### 3. Growth Scores Verification

```bash
# Check AWS API returns growth scores (not NULL)
curl -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/api/growth-scores
```

Expected:
- Status: 200
- Scores populated: > 80%
- Sample scores: CBIO (108.3%), CRGY (85.1%), etc.

### 4. Data Quality Checks

**AWS RDS:**
```sql
SELECT COUNT(*) as total, 
       COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as with_scores
FROM stock_scores;
-- Expected: > 3900/4711 (84%+)
```

**Dashboard:**
- Visit CloudFront URL
- Verify "Data not available" is GONE
- Check growth score panel shows values
- Verify circuit breaker metrics update

### 5. Loader Execution Verification

```bash
# Check ECS loader logs for successful execution
aws logs describe-log-groups --query 'logGroups[?contains(logGroupName, `algo`)]'

# Verify no schema errors
aws logs filter-log-events \
  --log-group-name /ecs/algo-market_health_daily-loader \
  --filter-pattern "ERROR" --max-items 10
```

Expected: No "column does not exist" errors

## Success Criteria

✅ **Infrastructure:** All 8 DynamoDB tables created
✅ **Lambda:** Orchestrator can acquire distributed locks (no lock acquisition errors)
✅ **Loaders:** ECS tasks complete without schema errors (ExitCode=0)
✅ **Data:** growth_score populated >80% in AWS RDS
✅ **API:** Dashboard API returns non-NULL growth_scores
✅ **UI:** Dashboard shows data, no "not available" errors

## Rollback Plan (if deployment fails)

1. Check CloudWatch logs: `/aws/lambda/algo-orchestrator-*`
2. Check ECS loader logs: `/ecs/algo-*-loader`
3. If DynamoDB not created:
   - Verify Terraform applied successfully
   - Check `terraform state list` for resource status
4. If loaders still failing:
   - Verify Docker images pushed successfully
   - Check ECS task definition has latest image digest
   - Verify schema migrations applied to RDS

## Files to Review Post-Deployment

- CloudWatch Logs: `/aws/lambda/algo-orchestrator-*`
- ECS Loader Logs: `/ecs/algo-*-loader`
- Terraform State: `terraform state show aws_dynamodb_table.orchestrator_locks`
- Database: Latest `algo_orchestrator_runs` records
