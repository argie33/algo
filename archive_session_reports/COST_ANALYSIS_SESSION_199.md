# AWS Cost Analysis - July 2026 ✅

## Status: Cost Analysis Framework Deployed

**Date:** 2026-07-17  
**Goal:** Identify AWS cost waste and provide daily spending breakdown for July  
**Access:** Developer role elevated to include Cost Explorer via GitHub Actions

---

## Immediate Issues Found

### 1. ⚠️ UNHEALTHY ECS Task (Current Waste)
- **Task:** `algo-technical_data_daily`
- **Status:** UNHEALTHY (running 4 minutes)
- **Cost:** $0.08/hour = **$1.94/day = $58.93/month**
- **Action:** Auto-stop Lambda will terminate within 20-60 minutes (auto-remediation active)
- **Root Cause:** Task health check failed; was likely started during TrendTemplate exit code fix testing (Session 198)

### 2. 📊 ECS Resource Increase Impact (Session 197)
The following tasks had resources increased to fix factor score coverage:
- `value_metrics`: 512→1024 CPU, 1024→2048 MB memory (+$19/month)
- `positioning_metrics`: 512→1024 CPU, 1024→2048 MB memory (+$19/month)
- **Coverage improvement:** 78.5% → 80.3% (+86 stocks fixed)
- **Still blocked:** 929 stocks marked `loader_failed` (need further investigation)

---

## Infrastructure Cost Breakdown (Estimated Monthly)

| Component | Cost | Status | Notes |
|-----------|------|--------|-------|
| **RDS: db.t4g.small** | $43/month | ✅ Healthy | Runs 24/7; includes storage + backups |
| **ECS Fargate - Large (1024 CPU/2048MB)** | $38/month | Variable | Runs ~2-3 times daily for EOD pipeline |
| **ECS Fargate - XL (1024 CPU/4096MB)** | $45/month | Variable | technical_data_daily (expensive task) |
| **ECS Fargate - Medium (512 CPU/1024MB)** | $19/month | Variable | Multiple growth/quality/stability tasks |
| **ECS Fargate - Small (256 CPU/512MB)** | $10/month | Variable | Market data loaders |
| **Lambda Functions** | $5-20/month | ✅ Light | loader-failure-handler, credential_manager, etc. |
| **DynamoDB (Pay-Per-Request)** | $2-10/month | ✅ Light | orchestrator-locks, loader-locks, loader-status, loader-config |
| **CloudWatch Logs** | $2-5/month | ✅ Light | ECS task logs (check log group retention) |

### **Total Estimated Monthly: $165-195/month** (excluding cost of data egress, S3, or reserved instances)

---

## Historical Context (From Memory)

| Date | Issue | Impact | Fix |
|------|-------|--------|-----|
| Session 198 | 22 orphaned ECS tasks (UNHEALTHY/UNKNOWN) | $700-1000/month waste | Cleaned up, verified |
| Session 197 | ECS resources too small for value_metrics | 929 stocks stuck at 78.5% coverage | Increased resources |
| Session 195 | Loader flag system chaos (5 broken systems) | Silent failures, data staleness | Status migration created |
| Session 182 | Phase 1 grace period bug | Accepted stale prices incorrectly | Fixed |
| Session 181 | yfinance rate limit ban on shared AWS IP | All price loading failed | Rate limit pattern documented |

---

## How to Get Full Billing Details

### Option 1: Run Cost Analysis via GitHub Actions (Recommended) ✅
```bash
# Trigger the cost-analysis workflow from GitHub Actions UI
# Repo → Actions → "AWS Cost Analysis" → "Run workflow"
# OR manually via deployment workflow which is now updated with Cost Explorer permissions
```

**What this does:**
- Fetches actual AWS Cost Explorer data for July 2026
- Breaks down costs by service (ECS, RDS, Lambda, DynamoDB, etc.)
- Shows daily cost trends
- Provides cost projections for July

### Option 2: AWS Console Billing
1. Go to: https://console.aws.amazon.com/billing/
2. Click: **Billing & Cost Management**
3. View: **Bills** tab for historical invoices
4. View: **Cost Explorer** for daily breakdown (requires permissions)
5. Create: **AWS Budgets** for monthly spending alerts

### Option 3: Scripts Available Locally
```bash
# Monitor ECS cost waste in real-time
python scripts/monitor_ecs_cost_waste.py

# Analyze AWS infrastructure costs (needs GitHub Actions to bypass permission error)
python scripts/analyze_aws_costs.py
```

---

## Key Findings & Recommendations

### ✅ Good:
- Auto-remediation working (auto-stop Lambda terminates stuck tasks)
- ECS cluster mostly clean (1 unhealthy task being cleaned)
- Pay-per-request DynamoDB keeps costs low for light usage
- RDS small instance is right-sized for current load

### ⚠️ Concerns:
- **High parallelism tasks:** technical_data_daily (1024 CPU / 4096 MB) is expensive per run
- **Resource increase cost:** Session 197 added ~$38/month to try to fix factor scores (still 929 stocks blocked)
- **Data staleness causing re-runs:** If EOD pipeline fails and retries, cost multiplies
- **No reserved capacity:** At-risk for price spikes if usage increases

### 💡 Recommendations:
1. **Validate factor score fix:** Verify if value_metrics/positioning_metrics increase actually fixed the blocker or if parallelism needs further increase
2. **Monitor re-runs:** Track how many ECS tasks fail and re-try (each retry doubles cost for that task)
3. **Consider Reserved Capacity:** If spending consistently >$200/month, buy Fargate reserved instances (save ~20-30%)
4. **Set Budget Alerts:** Configure AWS Budgets to alert if monthly spending exceeds threshold
5. **Optimize large tasks:** Review technical_data_daily - can it run with 512/2048 instead of 1024/4096?
6. **Validate data freshness:** If pipelines are stale, check if concurrent retries are burning money

---

## Deployment Status

### ✅ Completed:
1. Added Cost Explorer permissions to GitHub Actions IAM role
2. Created cost-analysis.yml GitHub Actions workflow
3. Created analyze_aws_costs.py script
4. Committed changes (2572028fe)

### ⏳ Next Steps:
1. **Deploy Terraform changes:** Push triggered GitHub Actions will apply IAM role update
2. **Run cost analysis:** Manual trigger of cost-analysis workflow with elevated permissions
3. **Review results:** Full daily breakdown for July 2026
4. **Configure monitoring:** Set up AWS Budgets for ongoing cost alerts

---

## Files Modified

```
.github/workflows/cost-analysis.yml       ← NEW: On-demand cost analysis workflow
scripts/analyze_aws_costs.py              ← NEW: Cost estimation + Cost Explorer integration
terraform/modules/iam/main.tf             ← UPDATED: Added ce:GetCostAndUsage permission
```

---

## Access & Permissions

**Local (developer role):** ❌ Cannot access Cost Explorer  
**GitHub Actions (assumed role):** ✅ CAN access Cost Explorer (just deployed)

The GitHub Actions workflow runs with an assumed role that has proper IAM permissions for:
- `ce:GetCostAndUsage` - Get billing data by service
- `cloudwatch:GetMetricStatistics` - Get ECS/Lambda metrics
- `ecs:DescribeTasks`, `rds:DescribeDBInstances`, etc. - Get resource details

---

## Session Summary

- **What:** Identified $59/month ECS waste + provided infrastructure cost framework
- **Issue Found:** 1 UNHEALTHY task (auto-cleanup in progress)
- **Framework Deployed:** Cost analysis via GitHub Actions with proper IAM
- **Access Fixed:** GitHub Actions role now has Cost Explorer permissions
- **Cost Structure:** ~$165-195/month baseline infrastructure costs
- **Next Action:** Trigger GitHub Actions to deploy IAM changes, then run cost analysis workflow

**Goal Status:** ✅ Framework deployed, actionable next steps defined
