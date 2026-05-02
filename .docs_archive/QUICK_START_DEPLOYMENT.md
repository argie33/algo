# Quick Start: Deploy Batch 5 in 45 Minutes

**Status:** All code ready. Follow this guide to deploy to AWS.

---

## Option A: Automated Deployment (Fastest)

### Prerequisites
- AWS CLI installed: `aws --version`
- AWS credentials configured: `aws configure`
- Credentials have CloudFormation, ECS, RDS, EC2 permissions

### Execute
```bash
# 1. Make script executable
chmod +x deploy-aws-batch5.sh

# 2. Run deployment
./deploy-aws-batch5.sh

# 3. Monitor CloudWatch logs
aws logs tail /ecs/loadquarterlyincomestatement --follow --region us-east-1
```

**Expected duration:** 45 minutes

---

## Option B: Manual AWS Console (No CLI Required)

### Follow This Checklist
[See MANUAL_AWS_DEPLOYMENT_CHECKLIST.md](MANUAL_AWS_DEPLOYMENT_CHECKLIST.md)

**Expected duration:** 60 minutes (more point-and-click)

---

## Option C: Hybrid Approach (Recommended)

### Use Console for CloudFormation (you can see UI feedback)
1. Use AWS Console to deploy 3 CloudFormation stacks
   - [MANUAL_AWS_DEPLOYMENT_CHECKLIST.md](MANUAL_AWS_DEPLOYMENT_CHECKLIST.md) - Phase 1

### Use AWS CLI for Remaining Steps
```bash
# 2. Configure Security Groups
RDS_SG=$(aws rds describe-db-instances --db-instance-identifier stocks-prod-db \
  --region us-east-1 --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' --output text)

ECS_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=stocks-ecs-tasks" \
  --region us-east-1 --query 'SecurityGroups[0].GroupId' --output text)

aws ec2 authorize-security-group-ingress --group-id "$RDS_SG" --protocol tcp --port 5432 \
  --source-security-group-id "$ECS_SG" --region us-east-1

# 3. Start Test Loader
aws ecs run-task --cluster stock-analytics-cluster \
  --task-definition loadquarterlyincomestatement --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx,subnet-yyyyy],securityGroups=[sg-zzzzz],assignPublicIp=ENABLED}" \
  --region us-east-1

# 4. Monitor
aws logs tail /ecs/loadquarterlyincomestatement --follow --region us-east-1
```

**Expected duration:** 45 minutes

---

## Detailed Timeline

```
Start
  ↓
Phase 1: Deploy CloudFormation Stacks (15 min)
  ├─ stocks-core (VPC) ..................... 5 min
  ├─ stocks-app (RDS) ..................... 10 min
  └─ stocks-app-ecs-tasks (ECS) .......... 5 min
  ↓
Phase 2: Configure Security Groups (5 min)
  └─ Allow ECS → RDS on port 5432
  ↓
Phase 3: Test First Loader (12 min)
  ├─ Start loadquarterlyincomestatement
  ├─ Monitor CloudWatch logs
  └─ Verify 25,000 rows in database
  ↓
Phase 4: Run All 6 Loaders in Parallel (12 min)
  ├─ Start all 6 tasks simultaneously
  ├─ Monitor all logs
  └─ Verify ~150,000 total rows
  ↓
Complete! ✓

Total: ~45 minutes
```

---

## Step-by-Step Execution

### STEP 1: Verify Prerequisites (2 min)

#### Option A: Using CLI
```bash
# Check AWS CLI
aws --version
# Should show: aws-cli/2.x.x

# Check credentials
aws sts get-caller-identity
# Should show your account ID and ARN
```

#### Option B: Using Console
```bash
# Go to: https://console.aws.amazon.com/
# Verify you can login
```

### STEP 2: Deploy CloudFormation Stacks (25 min)

#### Option A: Using Script
```bash
chmod +x deploy-aws-batch5.sh
./deploy-aws-batch5.sh
# Script will deploy all 3 stacks automatically
```

#### Option B: Using Console
Follow: [MANUAL_AWS_DEPLOYMENT_CHECKLIST.md - Phase 1](MANUAL_AWS_DEPLOYMENT_CHECKLIST.md)

**Verify:** All 3 stacks show `CREATE_COMPLETE`
```bash
aws cloudformation list-stacks --region us-east-1 \
  --stack-status-filter CREATE_COMPLETE --query 'StackSummaries[*].StackName'
# Should show: stocks-core, stocks-app, stocks-app-ecs-tasks
```

### STEP 3: Configure Security Groups (5 min)

```bash
# Get RDS security group
RDS_SG=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-prod-db \
  --region us-east-1 \
  --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
  --output text)

echo "RDS Security Group: $RDS_SG"

# Get ECS security group
ECS_SG=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=stocks-ecs-tasks" \
  --region us-east-1 \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

echo "ECS Security Group: $ECS_SG"

# Allow ECS to connect to RDS
aws ec2 authorize-security-group-ingress \
  --group-id "$RDS_SG" \
  --protocol tcp \
  --port 5432 \
  --source-security-group-id "$ECS_SG" \
  --region us-east-1 \
  --description "Allow ECS to RDS"
```

**Verify:** Rule appears in RDS security group

### STEP 4: Test First Loader (12 min)

```bash
# Start the task
echo "Starting first loader task..."
aws ecs run-task \
  --cluster stock-analytics-cluster \
  --task-definition loadquarterlyincomestatement \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxxxx,subnet-yyyyy],
    securityGroups=[sg-zzzzz],
    assignPublicIp=ENABLED
  }" \
  --region us-east-1

# Monitor logs (run in another terminal)
aws logs tail /ecs/loadquarterlyincomestatement --follow --region us-east-1
```

**Expected output:**
```
2026-04-29 14:00:00 - Starting loadquarterlyincomestatement (PARALLEL)
2026-04-29 14:00:15 - Loading income statements for 4969 stocks...
2026-04-29 14:02:30 - Progress: 500/4969 (10.5/sec, ~420s remaining)
2026-04-29 14:15:45 - [OK] Completed: 24950 rows inserted, 4969 successful, 0 failed
```

**Verify data:**
```bash
# Get RDS endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-prod-db \
  --region us-east-1 \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

# Connect and query
psql -h "$RDS_ENDPOINT" -U stocks -d stocks -c \
  "SELECT COUNT(*) as rows, COUNT(DISTINCT symbol) as symbols FROM quarterly_income_statement;"
```

**Expected:** ~25,000 rows, ~4,969 symbols

### STEP 5: Run All 6 Loaders (12 min)

Once first loader succeeds:

```bash
#!/bin/bash
LOADERS=("loadquarterlyincomestatement" "loadannualincomestatement"
         "loadquarterlybalancesheet" "loadannualbalancesheet"
         "loadquarterlycashflow" "loadannualcashflow")

echo "Starting all 6 Batch 5 loaders in parallel..."
for loader in "${LOADERS[@]}"; do
  echo "  Starting $loader..."
  aws ecs run-task \
    --cluster stock-analytics-cluster \
    --task-definition "$loader" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={
      subnets=[subnet-xxxxx,subnet-yyyyy],
      securityGroups=[sg-zzzzz],
      assignPublicIp=ENABLED
    }" \
    --region us-east-1 > /dev/null &
done

wait
echo "All 6 loaders started!"
```

**Monitor all:**
```bash
# Watch all loader logs
aws logs tail /ecs/ --follow --region us-east-1 | \
  grep -E "loadquarterly|loadannual|Progress|Completed"
```

**Verify final data:**
```bash
# All 6 tables should have ~25,000 rows each
psql -h "$RDS_ENDPOINT" -U stocks -d stocks << 'EOF'
SELECT 
  'quarterly_income_statement' as table_name,
  COUNT(*) as row_count
FROM quarterly_income_statement
UNION ALL
SELECT 'annual_income_statement', COUNT(*) FROM annual_income_statement
UNION ALL
SELECT 'quarterly_balance_sheet', COUNT(*) FROM quarterly_balance_sheet
UNION ALL
SELECT 'annual_balance_sheet', COUNT(*) FROM annual_balance_sheet
UNION ALL
SELECT 'quarterly_cash_flow', COUNT(*) FROM quarterly_cash_flow
UNION ALL
SELECT 'annual_cash_flow', COUNT(*) FROM annual_cash_flow
ORDER BY row_count DESC;
EOF
```

---

## Expected Results

### Performance
✓ Each loader: 7-12 minutes (vs 35-60 min baseline)
✓ All 6 parallel: ~12 minutes (vs 285 min serial)
✓ Speedup: **5x**

### Data
✓ ~25,000 rows per loader
✓ ~150,000 rows total (all 6)
✓ 4,969 unique symbols
✓ 0 errors in logs

### System Health
✓ CloudWatch logs show progress updates
✓ No SIGALRM errors
✓ No database connection errors
✓ CPU utilization: 60-80%

---

## Troubleshooting Quick Guide

### CloudFormation Stack Failed
```bash
# Check errors
aws cloudformation describe-stack-events \
  --stack-name stocks-core \
  --region us-east-1 \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]' \
  --output json

# Delete and retry
aws cloudformation delete-stack --stack-name stocks-core --region us-east-1
```

### Can't Connect to RDS
```bash
# Verify security group rule
aws ec2 describe-security-groups --group-ids "$RDS_SG" \
  --region us-east-1 \
  --query 'SecurityGroups[0].IpPermissions[*].[IpProtocol,FromPort,ToPort,UserIdGroupPairs[*].GroupId]'

# Should show: tcp, 5432, and the ECS security group ID
```

### Task Won't Start
```bash
# Check task definition
aws ecs describe-task-definition \
  --task-definition loadquarterlyincomestatement \
  --region us-east-1

# Check ECS cluster
aws ecs describe-clusters \
  --clusters stock-analytics-cluster \
  --region us-east-1
```

### No Data in Database
```bash
# Check task logs for errors
aws logs get-log-events \
  --log-group-name /ecs/loadquarterlyincomestatement \
  --log-stream-name <task-id> \
  --region us-east-1
```

---

## Key Configuration Values

You'll need these when prompted:

| Value | What to Use |
|-------|------------|
| RDSUsername | `stocks` |
| RDSPassword | `bed0elAn` |
| RDSPort | `5432` |
| ECS Cluster | `stock-analytics-cluster` |
| Launch Type | `FARGATE` |
| Public IP | `ENABLED` |
| AWS Region | `us-east-1` |

---

## Success Confirmation

When you see this, you're done ✓

```
[OK] Completed: 150000 rows inserted, 29814 successful, 0 failed in 750.5s (12.5m)
```

With data in database:
```
 table_name            | row_count
-----------------------|----------
 quarterly_income_statement | 24950
 annual_income_statement | 24950
 quarterly_balance_sheet | 24950
 annual_balance_sheet | 24950
 quarterly_cash_flow | 24950
 annual_cash_flow | 24950
-----------------------|----------
 TOTAL | 149700
```

---

## Next: Scale to All Loaders

Once Batch 5 is verified:

1. **Week 2:** Apply parallel pattern to 6 more loaders
2. **Week 3:** Apply to 12 price loaders
3. **Week 4:** Apply to remaining 28 loaders
4. **Result:** Full system speedup of 5x (300h → 60h)

---

## Documentation Reference

| Document | Use When |
|----------|----------|
| This file | Quick start deployment |
| MASTER_ACTION_PLAN.md | Need detailed step-by-step plan |
| AWS_ISSUES_AND_FIXES.md | Running into specific AWS issues |
| MANUAL_AWS_DEPLOYMENT_CHECKLIST.md | Using AWS Console (no CLI) |
| deploy-aws-batch5.sh | Running automated deployment script |

---

## Contact & Support

If you get stuck:
1. Check the troubleshooting section above
2. Review MANUAL_AWS_DEPLOYMENT_CHECKLIST.md for step-by-step console navigation
3. Check AWS CloudFormation events for error messages
4. Check ECS task logs in CloudWatch

---

**Ready to deploy? Start with Step 1 above. Expected completion: 45 minutes.**
