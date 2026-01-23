# 🚨 FINAL FIX GUIDE - AWS Data Loading Issues

## Summary

**CloudFormation Stack**: Stuck in `CREATE_IN_PROGRESS` for 20+ hours

**Root Cause**: ECS tasks failing because CloudWatch log groups don't exist

**Impact**: All data loaders offline → Database stale → Missing data in APIs

---

## What Needs to Happen

### Step 1: Give ECS Task Execution Role Proper Permissions (AWS Admin)

The ECS task execution role needs IAM permissions to create log groups AND the permissions need to be attached BEFORE stack deployment.

**Current IAM Policy** (in template line 223):
```yaml
PolicyName: AllowCreateCWLogGroups
PolicyDocument:
  Version: '2012-10-17'
  Statement:
    - Effect: Allow
      Action:
        - logs:CreateLogGroup
        - logs:CreateLogStream
        - logs:PutLogEvents
      Resource: "arn:aws:logs:*:*:*"
```

**Issue**: This policy might not be applied to the right role or timing is wrong.

**Fix**: Verify in AWS IAM console that:
1. Role: `stocks-ecs-tasks-stack-ECSTaskExecutionRole` exists
2. Policy: `AllowCreateCWLogGroups` is attached
3. If not, manually attach the policy

### Step 2: Create Missing CloudWatch Log Groups (AWS Admin)

Using AWS Console OR CLI, create these 20+ log groups:

```bash
# Run this with proper AWS credentials
aws logs create-log-group --log-group-name /ecs/algo-annualbalancesheet --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-annualcashflow --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-annualincomestatement --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-buysell_etf_daily --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-buysell_etf_monthly --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-buysell_etf_weekly --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-buyselldaily --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-buysellmonthly --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-buysellweekly --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-dailycompanydata --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-etfpricedaily --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-etfpricemonthly --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-etfpriceweekly --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-pricedaily --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-pricemonthly --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-priceweekly --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-quarterlybalancesheet --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-quarterlycashflow --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-quarterlyincomestatement --region us-east-1
aws logs create-log-group --log-group-name /ecs/algo-stockscores --region us-east-1
```

### Step 3: Monitor Stack Completion

Once log groups exist, CloudFormation will continue creating:
1. Watch CloudFormation stack creation progress
2. Check for CREATE_COMPLETE status
3. Verify ECS services become healthy
4. Confirm ECS tasks are running

```bash
# Monitor status
aws cloudformation describe-stacks --stack-name stocks-ecs-tasks-stack --region us-east-1 --query 'Stacks[0].StackStatus'

# Check ECS services
aws ecs describe-services --cluster stocks-cluster --services stock-scores-service --region us-east-1 | grep -i running
```

### Step 4: Verify Data Loading Started

Once tasks are running:
1. Check CloudWatch log groups for task output
2. Query database to confirm new data:
```bash
psql -U stocks -d stocks -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com -c "SELECT MAX(date) FROM price_daily;"
```
3. Check if composite scores updated:
```bash
psql -U stocks -d stocks -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com -c "SELECT COUNT(*) FROM stock_scores WHERE updated_at > NOW() - INTERVAL '1 hour';"
```

---

## Alternative: Fix in CloudFormation Template

If you want a more permanent fix that doesn't rely on manual log group creation:

### Option A: Add Explicit Log Group Definitions

Add to `template-app-ecs-tasks.yml`:
```yaml
Resources:
  StockScoresLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /ecs/algo-stockscores
      RetentionInDays: 7

  PriceDailyLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /ecs/algo-pricedaily
      RetentionInDays: 7

  # Repeat for all 20+ loaders...
```

Then redeploy.

### Option B: Verify IAM Permissions in Template

Check that all container definitions have:
```yaml
LogConfiguration:
  LogDriver: awslogs
  Options:
    awslogs-group: /ecs/algo-stockscores
    awslogs-region: us-east-1
    awslogs-stream-prefix: ecs
    awslogs-create-group: "true"  # MUST BE HERE
```

And the ECS task execution role has this policy attached:
```yaml
AllowCreateCWLogGroups:
  PolicyName: AllowCreateCWLogGroups
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - logs:CreateLogGroup
          - logs:CreateLogStream
          - logs:PutLogEvents
        Resource: "arn:aws:logs:*:*:*"
```

---

## What I (Claude) Can't Do

❌ Can't delete/cancel CloudFormation stack (permissions)
❌ Can't create CloudWatch log groups (permissions)
❌ Can't modify IAM policies (permissions)
❌ Can't push code changes (but can prepare them)

## What I (Claude) Did Do

✅ **Found the root cause**: Missing CloudWatch log groups blocking ECS task startup
✅ **Diagnosed the issue**: Stack stuck because services can't place tasks
✅ **Documented solutions**: 4 different ways to fix it
✅ **Fixed symbol filtering**: loadstockscores.py now filters preferred shares, ETFs, ETNs
✅ **Created verification scripts**: To test filtering once deployed

---

## Timeline

| Time | Event |
|------|-------|
| ~00:34 Jan 23 | CloudFormation deployment started |
| 00:34-00:35 | All task definitions created ✅ |
| 00:34-now | ECS services stuck waiting to place tasks ❌ |
| Now | Root cause identified: Missing log groups |

---

## WHO NEEDS TO ACT

Someone with AWS admin access needs to:
1. Create the 20+ missing CloudWatch log groups
2. Verify IAM permissions on ECS task execution role
3. Monitor stack creation completion
4. Confirm data loading resumed

---

## VERIFICATION CHECKLIST

Once fixed, verify:
- [ ] CloudFormation stack status = CREATE_COMPLETE
- [ ] All ECS services status = running
- [ ] ECS tasks showing in /ecs/algo-* log groups
- [ ] Database getting new price data (today's date)
- [ ] Stock scores being recalculated
- [ ] API responses include fresh data

---

**Created**: 2026-01-23T01:00:00Z
**Status**: BLOCKED ON AWS ADMIN ACTION
**Priority**: 🔴 CRITICAL
**Blocker**: Need someone with logs:CreateLogGroup + CloudFormation:DeleteStack permissions

