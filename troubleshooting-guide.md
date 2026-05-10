# Troubleshooting Guide

## Quick Diagnosis: Is the System Healthy?

Run the health check workflow (read-only, no changes):
```bash
gh workflow run check-stack-status.yml
```

Or manually:
```bash
# Check all stacks are deployed
aws cloudformation list-stacks --region us-east-1 \
  --query 'StackSummaries[?StackStatus==`CREATE_COMPLETE` || StackStatus==`UPDATE_COMPLETE`].StackName'

# Check Lambda can be invoked
aws lambda invoke --function-name algo-orchestrator --region us-east-1 /tmp/out.json

# Check RDS is accessible (from Bastion)
psql -h <RDS_ENDPOINT> -U stocks -d stocks -c "SELECT 1;"
```

---

## Deployment Issues

### Workflow Hung/Failed

**Symptom:** Deployment stuck for 10+ minutes or failed with error

**Diagnosis:**
1. Check workflow logs: https://github.com/argie33/algo/actions
2. Scroll to FIRST error (not the last one — earlier errors cause cascades)
3. Look for "Resource creation cancelled" (indicates upstream failure)

**Common Root Causes & Fixes:**

| Error | Cause | Fix |
|-------|-------|-----|
| `"Unable to locate credentials"` | AWS credentials not set in GitHub Secrets | Set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ACCOUNT_ID` in repo settings |
| `"User is not authorized to perform: cloudformation:*"` | IAM user lacks CloudFormation permissions | Add CloudFormation, EC2, RDS, Lambda, ECS, IAM permissions to IAM user |
| `"OIDC provider not found"` | Bootstrap not run yet | Run `gh workflow run bootstrap-oidc.yml` |
| `"Stack already exists"` | Previous deployment left stack in bad state | Run `cleanup-orphaned-resources.yml` then retry |
| `"Insufficient capacity"` | AWS ran out of resources in us-east-1 | Try again (capacity issue resolves), or switch region |
| `"Parameter validation failed"` | CloudFormation parameter invalid | Check CloudWatch logs, see what parameter was rejected |

**Recovery:**
```bash
# Check what's deployed
aws cloudformation describe-stacks --region us-east-1 \
  --query 'Stacks[*].[StackName,StackStatus]' --output table

# If a stack is in bad state (ROLLBACK_IN_PROGRESS, etc.)
# Delete it and retry deployment
aws cloudformation delete-stack --stack-name stocks-core --region us-east-1
gh workflow run deploy-all-infrastructure.yml
```

### Deployment Cost Spike

**Symptom:** Unexpected AWS charges

**Diagnosis:**
1. Check CloudFormation stacks: `aws cloudformation list-stacks --region us-east-1`
2. Look for duplicate stacks (e.g., `stocks-core`, `stocks-core-old`)
3. Check RDS instance: `aws rds describe-db-instances --region us-east-1`
4. Check ECS tasks: `aws ecs list-tasks --cluster stocks-data-cluster --region us-east-1`

**Common Issues & Fixes:**

| Issue | Cause | Fix |
|-------|-------|-----|
| Multiple RDS instances | Failed deployment left old instance | Delete orphaned RDS: `aws rds delete-db-instance --skip-final-snapshot` |
| Duplicate Lambda functions | Old code not cleaned | Run `cleanup-orphaned-resources.yml` |
| High data transfer costs | ECS tasks pulling from internet | (Already fixed: VPC endpoints used, no NAT) |

---

## Database Issues

### RDS Connection Failed

**Symptom:** `psql: could not connect to server: Connection refused` or `timeout`

**Diagnosis:**
1. Check RDS is running:
   ```bash
   aws rds describe-db-instances --db-instance-identifier stocks-data-rds \
     --region us-east-1 --query 'DBInstances[0].DBInstanceStatus'
   ```

2. Check security group allows port 5432:
   ```bash
   aws ec2 describe-security-groups --region us-east-1 \
     --filters Name=tag:Name,Values=*rds* --query 'SecurityGroups[*].IpPermissions'
   ```

3. Check RDS is in private subnet (correct architecture):
   ```bash
   aws ec2 describe-db-instances --db-instance-identifier stocks-data-rds \
     --region us-east-1 --query 'DBInstances[0].DBSubnetGroup'
   ```

**Fixes:**
```bash
# If security group is missing 5432 inbound rule:
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx --protocol tcp --port 5432 \
  --source-security-group sg-yyyyy --region us-east-1

# If RDS is down, restart it:
aws rds reboot-db-instance --db-instance-identifier stocks-data-rds \
  --region us-east-1
```

### Database Full / Out of Space

**Symptom:** INSERT operations fail with "no space left on device"

**Diagnosis:**
```bash
# Check RDS storage
aws rds describe-db-instances --db-instance-identifier stocks-data-rds \
  --region us-east-1 --query 'DBInstances[0].[AllocatedStorage,FreeStorageSpace]'

# Check what's consuming space
psql -h <RDS_ENDPOINT> -U stocks -d stocks -c "\dt+ stocks.*"
```

**Fixes:**
```bash
# Clean up old logs (keep 7 days, archive rest to S3)
DELETE FROM algo_audit_log WHERE created_at < NOW() - INTERVAL '30 days';

# Vacuum to reclaim space
VACUUM ANALYZE;

# Increase RDS storage (no downtime)
aws rds modify-db-instance --db-instance-identifier stocks-data-rds \
  --allocated-storage 100 --region us-east-1
```

### Data Stale (No Price Updates Today)

**Symptom:** Latest data is from yesterday; loaders not running

**Diagnosis:**
```bash
# Check latest price data
psql -h localhost -U stocks -d stocks \
  -c "SELECT symbol, date, close FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL '2 days' ORDER BY date DESC LIMIT 5;"

# Check ECS loader logs
aws logs tail /ecs/stocks-data-cluster --since 2h --region us-east-1 | grep -i error
```

**Fixes:**
```bash
# Manually trigger a loader (pick one)
# Option 1: Via AWS Console (ECS → Run task)
# Option 2: Via CLI
aws ecs run-task \
  --cluster stocks-data-cluster \
  --task-definition stocks-loaders:1 \
  --region us-east-1

# Option 3: Via local Docker (fastest)
cd /mnt/c/Users/arger/code/algo
docker-compose up  # Starts all loaders in background
```

---

## Lambda & Trading Issues

### Algo Lambda Not Executing

**Symptom:** 5:30pm ET passed, but no trades executed

**Diagnosis:**
```bash
# Check EventBridge Scheduler
aws scheduler list-schedules --region us-east-1 \
  --query 'Schedules[?contains(Name, `algo`)]'

# Check Lambda logs
aws logs tail /aws/lambda/algo-orchestrator --since 1h --region us-east-1

# Check Lambda function exists and is accessible
aws lambda get-function --function-name algo-orchestrator --region us-east-1
```

**Common Issues & Fixes:**

| Issue | Cause | Fix |
|-------|-------|-----|
| Schedule disabled | EventBridge scheduler paused | Enable: `aws scheduler update-schedule --name algo-daily --state ENABLED` |
| Lambda timeout (5 min) | Algo taking too long | Increase timeout: `aws lambda update-function-configuration --function-name algo-orchestrator --timeout 900` |
| Alpaca auth failing | API keys expired or invalid | Update in Secrets Manager: `aws secretsmanager update-secret --secret-id stocks-algo-secrets --secret-string '{...}'` |
| Market closed (weekends) | Running outside market hours | EventBridge set to weekdays only (correct), no issue |
| Lambda execution failed | Code error or database issue | Check CloudWatch logs: `aws logs tail /aws/lambda/algo-orchestrator` |

**Manual Trigger (For Testing):**
```bash
aws lambda invoke --function-name algo-orchestrator \
  --region us-east-1 /tmp/out.json && cat /tmp/out.json
```

### Trade Not Executing Despite Signals

**Symptom:** Signals found, but trade didn't execute

**Diagnosis:**
1. Check algo audit log:
   ```bash
   psql -h localhost -U stocks -d stocks \
     -c "SELECT phase, message FROM algo_audit_log WHERE created_at > NOW() - INTERVAL '1 day' ORDER BY created_at DESC LIMIT 20;"
   ```

2. Check filter results:
   ```bash
   psql -h localhost -U stocks -d stocks \
     -c "SELECT symbol, t1_score, t2_score, t3_score FROM algo_signals_evaluated WHERE date = CURRENT_DATE ORDER BY t5_final_rank;"
   ```

3. Check circuit breakers:
   ```bash
   psql -h localhost -U stocks -d stocks \
     -c "SELECT * FROM algo_audit_log WHERE phase = 'CIRCUIT_BREAKER' AND created_at > NOW() - INTERVAL '1 day';"
   ```

**Common Filters That Block Trades:**

| Filter | Block Reason | Fix |
|--------|-------------|-----|
| **Tier 3 (Stage 2)** | Stock not in uptrend | Only buy in uptrends (correct behavior) |
| **Circuit Breaker** | Drawdown > limit | Reduce position size or risk limits in algo_config.py |
| **Position Limit** | Already at max positions | Close some positions or raise max_positions |
| **Duplicate Signal** | Same signal on same day | (Prevents double-buying—correct) |
| **Alpaca Insufficient Funds** | Cash not enough for trade size | Increase Alpaca paper account size or reduce position size |

### Trade Executed, But Not Synced to Alpaca

**Symptom:** Database shows trade but no order in Alpaca

**Diagnosis:**
```bash
# Check local trade record
psql -h localhost -U stocks -d stocks \
  -c "SELECT * FROM algo_trades WHERE created_at > NOW() - INTERVAL '1 day' ORDER BY created_at DESC LIMIT 5;"

# Check Alpaca orders (via API)
python3 -c "
from alpaca_trade_api import REST
import os
api = REST(os.getenv('APCA_API_KEY_ID'), os.getenv('APCA_API_SECRET_KEY'), base_url=os.getenv('APCA_API_BASE_URL'))
orders = api.list_orders(status='all')
for o in orders[-5:]:
    print(f'{o.symbol} {o.qty} @ {o.filled_avg_price} ({o.status})')
"
```

**Fixes:**
```bash
# If trade exists in DB but not in Alpaca, manually create order:
python3 -c "
from alpaca_trade_api import REST
import os
api = REST(os.getenv('APCA_API_KEY_ID'), os.getenv('APCA_API_SECRET_KEY'), base_url=os.getenv('APCA_API_BASE_URL'))
order = api.submit_order(symbol='AAPL', qty=10, side='buy', type='market', time_in_force='day')
print(f'Order: {order.id}')
"
```

---

## Local Development Issues

### Docker Won't Start

**Symptom:** `docker-compose up` fails

**Diagnosis:**
```bash
docker --version  # Is Docker installed?
docker-compose ps  # Are services running?
docker logs stocks-postgres  # Check postgres logs
```

**Common Issues & Fixes:**

| Error | Cause | Fix |
|-------|-------|-----|
| `Cannot connect to Docker daemon` | Docker Desktop not running | Start Docker Desktop |
| `network database declared as external but could not be found` | Network missing | `docker network create algo-network` |
| `Port 5432 already in use` | Another PostgreSQL running | `lsof -i :5432` and kill, or change port in docker-compose.yml |
| `Healthcheck failed` | Postgres not ready | Wait 30 seconds, try again |

### Local Algo Fails at Data Freshness Check

**Symptom:** `algo_run_daily.py` fails immediately: "Data too stale"

**Diagnosis:**
```bash
# Check what data exists locally
psql -h localhost -U stocks -d stocks \
  -c "SELECT symbol, MAX(date) FROM price_daily GROUP BY symbol ORDER BY MAX(date) LIMIT 10;"
```

**Fix:**
```bash
# Load fresh data via loaders
cd /mnt/c/Users/arger/code/algo
python3 loadpricedaily.py  # Fetch today's prices
python3 loadstockscores.py  # Compute technical indicators
```

Or trigger via ECS (if AWS deployed):
```bash
aws ecs run-task --cluster stocks-data-cluster --task-definition stocks-loaders:1 --region us-east-1
```

### "psycopg2: autocommit" Error

**Symptom:** `psycopg2.errors.InsufficientPrivilege: permission denied for schema stocks`

**Diagnosis:** Database connection not in autocommit mode

**Fix:** Already fixed in stock_scores_loader.py (commit aws_transaction_fix.md). If you're using old code, update to use autocommit:
```python
conn.autocommit = True
```

---

## Quick Reference: What File to Check When

| Problem | Check File |
|---------|-----------|
| Algo not trading | algo_audit_log table, CloudWatch /aws/lambda/algo-orchestrator |
| Data missing | algo_data_freshness.py, loadpricedaily.py output |
| Signals generated but trades blocked | algo_filter_pipeline.py tier 3 filter, circuit breaker logs |
| API returning 500 errors | CloudWatch /aws/lambda/rest-api |
| Frontend not loading | CloudFront cache, Cognito auth |
| RDS taking forever | CloudWatch RDS CPU/connections metrics |
| Cost spiking | CloudFormation stacks (check for duplicates), RDS instance size |

---

**Last Updated:** 2026-05-07
**For additional context:** See memory files in .claude/projects/*/memory/ (especially aws_deployment_state, production_blockers_fixed, end_to_end_verification)
