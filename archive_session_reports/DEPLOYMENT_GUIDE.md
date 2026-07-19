# Deployment Guide - Clean Infrastructure Setup

**Status:** Ready to deploy to new AWS account  
**Cost:** ~$35-45/month (from $100-150/month)  
**What changed:** Removed VPC Lambda, right-sized everything, disabled unnecessary features

---

## Prerequisites

1. **New AWS account with billing verified**
2. **AWS CLI configured** with access to the new account
3. **Terraform installed** (v1.3+)
4. **Git** (changes already committed)

---

## Step 1: Verify Configuration (Take 2 min)

```bash
# Check that clean IaC is in place
cd terraform
terraform fmt -recursive .
terraform validate

# Expected: No errors, clean syntax
```

---

## Step 2: Initialize Terraform

```bash
cd terraform

# Initialize Terraform backend (S3 + DynamoDB for state locking)
terraform init

# You may be prompted to configure:
# - AWS region: us-east-1
# - AWS credentials: Use your new account credentials
```

---

## Step 3: Plan Deployment

```bash
# Review what will be created
terraform plan -var-file=terraform.tfvars -out=plan.tfplan

# Look for:
# + RDS PostgreSQL (db.t4g.small)
# + Lambda functions (api, algo)
# + ECS cluster + task definitions
# + S3 buckets (state, frontend)
# + CloudWatch log groups

# Should NOT see:
# - VPC Endpoints (would add $43/mo)
# - RDS Proxy (would add $150-300/mo)
# - Provisioned concurrency (would add $12/mo)
# - Multi-AZ RDS (would add $15/mo)
```

---

## Step 4: Deploy Infrastructure

```bash
# Create all AWS resources
terraform apply plan.tfplan

# Monitor output for:
# ✓ RDS endpoint
# ✓ Lambda function ARNs
# ✓ API Gateway endpoint
# ✓ ECS cluster name

# Time: 5-10 minutes
```

---

## Step 5: Verify Deployment

```bash
# Get outputs
terraform output

# Test RDS connectivity
RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
psql -h $RDS_ENDPOINT -U stocks -d stocks -c "SELECT 1"
# Expected: (1 row)

# Test Lambda
aws lambda list-functions --query 'Functions[].FunctionName' | grep -i algo
# Expected: stocks-api-dev, stocks-algo-dev

# Test ECS cluster
aws ecs list-clusters --query 'clusterArns[]'
# Expected: algo-cluster
```

---

## Step 6: Run Data Loaders Locally

```bash
# Loaders run on YOUR machine, not in AWS
# This keeps costs down ($0.10/mo vs $50+/mo for Lambda/ECS)

# Terminal 1: Start PostgreSQL (or RDS is ready)
# Already done: RDS created and running in AWS

# Terminal 2: Run local orchestrator
cd scripts
python3 run_local_orchestrator.py --run-all

# Expected output:
# [INFO] Connecting to RDS at $RDS_ENDPOINT
# [INFO] Running morning pipeline...
# [INFO] Loading prices...
# [INFO] Running algo...
# [SUCCESS] Morning pipeline completed

# Terminal 3: Start dashboard
python3 dashboard.py

# Expected: Dashboard opens on http://localhost:5173
# Data from AWS RDS displays
```

---

## Step 7: Verify Data Flow

```bash
# Check data loaded into RDS
psql -h $RDS_ENDPOINT -U stocks -d stocks << 'EOF'
SELECT 'prices' as table_name, COUNT(*) as rows FROM prices
UNION ALL
SELECT 'portfolios', COUNT(*) FROM portfolios
UNION ALL
SELECT 'positions', COUNT(*) FROM positions;
EOF

# Expected: Rows > 0 for each table
```

---

## Cost Breakdown (Monthly)

| Component | Cost | Notes |
|-----------|------|-------|
| RDS PostgreSQL | $25-30 | db.t4g.small, single-AZ, 1-day backups |
| Lambda (API + Algo) | $2-3 | Public, no VPC, minimal invocations |
| CloudWatch Logs | $1-2 | 1-day retention |
| S3 (state + data) | $1-2 | Minimal usage |
| **TOTAL** | **$35-45** | Down from $100-150/mo |

---

## What Runs Where

| Component | Location | Cost | Frequency |
|-----------|----------|------|-----------|
| Data loaders | Your machine (cron job) | $0 | 2x daily (morning + evening) |
| Algo execution | Your machine (cron job) | $0 | 2x daily |
| Database | AWS RDS | $25-30 | Always on |
| Dashboard | Your machine (python dashboard.py) | $0 | On demand |
| API Lambda | AWS | $2-3 | Only if dashboard runs in cloud |

---

## Maintenance

### Weekly
```bash
# Check data freshness
psql -h $RDS_ENDPOINT -U stocks -d stocks -c \
  "SELECT MAX(date) as latest_price_date FROM prices"

# Should be today (or last trading day)
```

### Monthly
```bash
# Review AWS costs
aws ce get-cost-and-usage \
  --time-period Start=2026-07-01,End=2026-08-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
```

### When Scaling (Future)
If you add more users or more frequent runs:
1. Move loaders to **ECS Fargate Spot** ($0.10-1/mo)
2. Move dashboard to **cloud** (add API Gateway, $1-2/mo)
3. Add **monitoring Lambdas** ($5-10/mo)
4. Everything scales without code changes

---

## Troubleshooting

### "psql: could not translate host name"
```bash
# RDS endpoint not ready yet, wait 2-3 minutes
# Or check security group allows your IP
```

### Lambda can't connect to RDS
```bash
# Lambda was in VPC in old setup, now public
# Make sure Lambda has internet access (API Gateway route)
# RDS must allow inbound from Lambda security group
```

### Dashboard shows "Data not available"
```bash
# 1. Verify RDS has data: psql query above
# 2. Check dashboard is using correct RDS endpoint
# 3. Verify credentials in ~/.aws/credentials
```

---

## Rollback (If Needed)

```bash
# Delete everything and start over
terraform destroy -var-file=terraform.tfvars

# Answer 'yes' to confirmation
# Time: 2-3 minutes
```

---

## Next Steps

1. ✅ Deploy infrastructure (this guide)
2. ✅ Run local orchestrator (2x daily via cron)
3. ✅ View dashboard (local or cloud)
4. Scale: Add users, increase frequency, migrate to cloud

---

**Questions?** Check CLAUDE.md or steering/ docs for more details.
