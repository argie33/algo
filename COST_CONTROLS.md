# COST CONTROL SAFEGUARDS

## Critical: Stop All AWS Auto-Deployments

### 1. GitHub Actions - DISABLE AUTO-DEPLOY
Edit `.github/workflows/deploy-app-stocks.yml`:
- REMOVE the `push:` trigger (lines 22-29)
- Keep ONLY `workflow_dispatch:` (manual trigger only)
- This prevents automatic deployments on code push

### 2. ECS Services - Set DesiredCount to 0
All ECS services should have `DesiredCount: 0` by default:
```yaml
StockScoresService:
  Type: AWS::ECS::Service
  Properties:
    DesiredCount: 0  # DO NOT AUTO-START
```

### 3. CloudFormation - Add DeletionPolicy
All expensive resources must have explicit deletion:
```yaml
DBInstance:
  Type: AWS::RDS::DBInstance
  DeletionPolicy: Delete  # ALWAYS delete on stack removal
```

### 4. Cost Alerts - CloudWatch Billing Alarm
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name DailyAWSCostAlert \
  --alarm-description "Alert if daily spend exceeds $50" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 86400 \
  --threshold 50 \
  --comparison-operator GreaterThanThreshold
```

### 5. Manual Deploy Process (SAFE)
```bash
# Step 1: Verify what will deploy
git status
git diff

# Step 2: Manual trigger GitHub Actions
# Go to: https://github.com/argie33/algo/actions
# Click "Data Loaders Pipeline" → "Run workflow"
# Set environment to "dev" (NOT prod)

# Step 3: Monitor for 15 minutes
# Go to CloudFormation console
# Check stack status real-time

# Step 4: Stop immediately if any errors
# CloudFormation Console → Delete Stack
```

## Local Testing ONLY

Use LOCAL loaders without AWS:
```bash
# Safe - doesn't touch AWS
python3 loadpricedaily.py
python3 loadstockscores.py

# NOT SAFE - can trigger AWS deployments
git push origin main              # DON'T DO THIS
```

## If Cost Spike Happens Again

1. **IMMEDIATELY** go to AWS Console
2. CloudFormation → Delete `stocks-ecs-tasks-stack`
3. ECS → Tasks → Stop all running tasks
4. Contact AWS Support with dates/times

---
**REMEMBER: Local testing is FREE. AWS deployments cost money.**
