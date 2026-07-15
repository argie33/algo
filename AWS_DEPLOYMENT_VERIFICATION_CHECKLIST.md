# AWS Deployment Verification Checklist

**Session 162 — 2026-07-15**

After GitHub Actions completes the deployment of commits (55cfce1aa, 816dd13a9, 75053bad1, etc.), use this checklist to verify fixes work in AWS.

## 1. GitHub Actions Deployment Status

```bash
# Check if deployment succeeded
gh run list --repo argeropolos/algo --limit 10 --json status,conclusion,name

# Look for: conclusion=SUCCESS for most recent terraform/deploy workflows
# Expected: Terraform apply + Lambda deploy + Docker build + ECS update
```

**Expected Status**: All deploy workflows show SUCCESS

---

## 2. Lambda Orchestrator Deployment

```bash
# Check Lambda last modified time (should be recent)
aws lambda get-function --function-name algo-orchestrator --region us-east-1 \
  --query 'Configuration.[LastModified, CodeSha256]'

# Check Lambda environment variables are set correctly
aws lambda get-function-configuration --function-name algo-orchestrator \
  --region us-east-1 --query 'Environment.Variables'

# Expected: ORCHESTRATOR_EXECUTION_MODE=paper (or auto)
# Expected: LastModified should be within last hour (after GH Actions ran)
```

---

## 3. EventBridge Schedulers Status

```bash
# Check morning and EOD orchestrator schedules
aws scheduler list-schedules --name-prefix algo-schedule \
  --region us-east-1 --query 'Schedules[*].[Name, State]'

# Expected output (all ENABLED):
#   algo-schedule-morning-dev, ENABLED
#   algo-schedule-eod-dev, ENABLED
#   (others: premarket, afternoon optional)
```

**Critical**: If State=DISABLED, run:
```bash
aws scheduler update-schedule --name algo-schedule-morning-dev \
  --region us-east-1 --state ENABLED
```

---

## 4. AWS RDS Data Freshness

```bash
# Connect to RDS (requires VPC access or RDS proxy endpoint)
psql -h <RDS_ENDPOINT> -U stocks -d stocks

# Check price data
SELECT MAX(date) as latest_prices FROM price_daily;
# Expected: Today's date or yesterday (trading hours)

# Check portfolio snapshot (Session 161 fix verification)
SELECT snapshot_date, position_count, unrealized_pnl_winning_count, 
       unrealized_pnl_losing_count
FROM algo_portfolio_snapshots
ORDER BY snapshot_date DESC LIMIT 3;
# Expected: position_count matches wins+loses+breakeven (no inconsistencies)

# Check risk metrics (portfolio beta)
SELECT report_date, portfolio_beta, var_pct_95
FROM algo_risk_daily
ORDER BY report_date DESC LIMIT 3;
# Expected: portfolio_beta values (0.0 for empty portfolio is correct)
```

---

## 5. Lambda Orchestrator Execution Logs

```bash
# Check recent Lambda invocations
aws lambda list-functions --region us-east-1 \
  --query 'Functions[?FunctionName==`algo-orchestrator`].FunctionArn'

# Get recent executions
aws logs describe-log-streams --log-group-name /aws/lambda/algo-orchestrator \
  --region us-east-1 --order-by LastEventTime --descending \
  --query 'logStreams[0:3].[logStreamName, lastEventTimestamp]'

# Check for errors in latest execution
aws logs get-log-events \
  --log-group-name /aws/lambda/algo-orchestrator \
  --log-stream-name '<LATEST_STREAM_NAME>' \
  --region us-east-1 \
  --query 'events[?contains(message, `ERROR`) || contains(message, `CRITICAL`)]'
```

**Expected**: Latest execution timestamp within last 24 hours, no ERROR/CRITICAL in logs

---

## 6. ECS Fargate Loaders Status

```bash
# Check loader task definitions
aws ecs list-task-definitions --family-prefix algo-loader \
  --region us-east-1 --query 'taskDefinitionArns[-3:]'

# Check most recent task runs
aws ecs list-tasks --cluster algo-cluster --region us-east-1 \
  --query 'taskArns[:5]'

# For each task, check status
aws ecs describe-tasks --cluster algo-cluster \
  --tasks <TASK_ARN> --region us-east-1 \
  --query 'tasks[0].[taskArn, lastStatus, stoppedReason]'
```

**Expected**: Tasks showing lastStatus=STOPPED with no errors, or RUNNING (active loaders)

---

## 7. Portfolio Snapshot Consistency (Session 161 Fix)

Use RDS query from Section 4 to verify:

```sql
-- Check for inconsistency (Session 161 was fixing this)
SELECT snapshot_date, position_count,
       (unrealized_pnl_winning_count + unrealized_pnl_losing_count + unrealized_pnl_breakeven_count) as total_positions
FROM algo_portfolio_snapshots
WHERE position_count != (unrealized_pnl_winning_count + unrealized_pnl_losing_count + unrealized_pnl_breakeven_count)
  AND snapshot_date >= CURRENT_DATE - INTERVAL '7 days';

-- Expected: Empty result (no inconsistencies)
```

---

## 8. Portfolio Beta (User Investigation)

Use RDS query:
```sql
SELECT report_date, portfolio_beta, position_count, 
       (SELECT COUNT(*) FROM algo_positions WHERE status='open') as db_open_positions
FROM algo_risk_daily
LEFT JOIN algo_portfolio_snapshots USING (report_date)
ORDER BY report_date DESC LIMIT 5;

-- Expected: portfolio_beta matches position context (0.0 when 0 positions)
```

**Note**: Portfolio beta of 0.0 is CORRECT for paper trading account with no open positions.  
Not a bug - this is the expected behavior.

---

## 9. Dashboard API Endpoints (Optional)

```bash
# If you have API Gateway endpoint
curl -s https://<API_GATEWAY_ID>.execute-api.us-east-1.amazonaws.com/prod/api/algo/metrics \
  -H "Authorization: Bearer <TOKEN>" | jq '.data'

# Expected fields: portfolio_beta, var_pct_95, top_5_concentration
```

---

## 10. CloudWatch Alarms

```bash
# Check if any alarms have been triggered
aws cloudwatch describe-alarms --region us-east-1 \
  --query 'MetricAlarms[?StateValue==`ALARM`].[AlarmName, StateReason]'

# Check Lambda errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=algo-orchestrator \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 --statistics Sum --region us-east-1
```

---

## Summary

| Component | Check | Expected | Status |
|-----------|-------|----------|--------|
| GitHub Actions | Deploy workflows | All SUCCESS | [ ] |
| Lambda Orchestrator | LastModified | Within last hour | [ ] |
| EventBridge | Morning/EOD state | ENABLED | [ ] |
| RDS Prices | MAX(date) | Today or yesterday | [ ] |
| RDS Snapshots | Consistency | No mismatches | [ ] |
| RDS Risk Metrics | portfolio_beta | Present, matches context | [ ] |
| Lambda Logs | Errors | None in last 24h | [ ] |
| ECS Loaders | Recent runs | No failures | [ ] |

---

## Troubleshooting

**If prices are stale (older than 24 hours):**
1. Check EventBridge scheduler is ENABLED (Section 3)
2. Check ECS loader logs (Section 6) for failures
3. Manually trigger morning pipeline (Section 4):
   ```bash
   aws stepfunctions start-execution \
     --state-machine-arn arn:aws:states:us-east-1:<ACCOUNT>:stateMachine:algo-morning-pipeline \
     --name manual-refresh-$(date +%s) --region us-east-1
   ```

**If Lambda orchestrator isn't executing:**
1. Check EventBridge triggers (Section 3)
2. Check Lambda permissions (Section 5)
3. Check for stale DynamoDB locks:
   ```bash
   python scripts/clear_stale_orchestrator_lock.py
   ```

**If portfolio_beta is NULL in API:**
1. Check algo_risk_daily table (Section 4, risk metrics query)
2. Verify orchestrator Phase 9 completed (Section 5 Lambda logs)
3. Check if algorithm ran: Look for "Computing circuit breaker metrics" in logs
