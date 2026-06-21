# AWS Cost Audit: Development Environment Waste Analysis

**Date:** 2026-06-21  
**Environment:** `dev` (paper trading, development only)  
**Estimated Monthly Spend:** $110-150

---

## 🔴 CRITICAL COST ISSUES (Act Now)

### 1. NAT Gateway: $32-40/month (BIGGEST WASTE)

**Current State:**
- 1 NAT gateway in public subnet (terraform/modules/vpc/main.tf:85-95)
- Fixed cost: $0.045/hour = ~$32/month
- Plus data transfer: ~$0.045/GB outbound

**Why It's Wasteful:**
- This is a **development environment** (terraform.tfvars:5: `environment = "dev"`)
- NAT gateway needed because Lambda/RDS are in private subnets and need internet
- But in dev, high availability isn't needed

**Fix Options (In Priority Order):**

1. **Option A: Remove NAT, use EC2 bastion + port forwarding** (saves ~$32/month)
   - Keep 1 bastion in public subnet
   - SSH tunnel for local dev access
   - Loaders run inside private subnets (use RDS proxy)
   - Cost: t3.micro bastion (~$6-8/month) + shutdown schedule

2. **Option B: VPC Endpoints for critical services** (saves ~$20/month, costs ~$7-10/month)
   - Keep NAT for now, add S3 + Secrets Manager endpoints
   - Reduces data transfer costs
   - Still need NAT for Alpaca API calls (external)

3. **Option C: Architecture redesign** (saves ~$32/month + saves Lambda processing)
   - Move to public subnets (dev only - RISKY)
   - Or use API Gateway HTTP_PROXY instead of VPC Lambda
   - Not recommended: breaks security model

**Recommendation:** **Option A** (bastion + port forwarding) = Save $32/month with better dev experience

---

### 2. Execution Monitor Lambda: $0.30-0.50/month (Low Cost, No Business Value)

**Current State:**
- terraform/modules/services/execution-monitor.tf:160
- Runs **every 2 hours, 10 AM-9 PM ET** = 6 invocations/day
- Schedule: `cron(0 10-21/2 ? * MON-FRI *)`
- Enabled in terraform.tfvars:81: `enable_execution_monitor = true`

**Why It's Wasteful:**
- Queries RDS for signals + Alpaca for trades
- **Paper trading environment** (alpaca_paper_trading = true)
- Not useful in dev: we have dashboards, CloudWatch logs, databases
- 252 trading days/year × 6 invocations = 1,512 wasted runs/year

**Fix:**
```hcl
# In terraform.tfvars, set:
enable_execution_monitor = false
```

**Savings:** ~$0.50/month (negligible) + cleaner logs

---

### 3. Weight Optimization Daily Task: $0.30/month (Low Cost, Maybe Useful)

**Current State:**
- terraform/modules/services/2x-daily-orchestrator.tf:218-248
- Runs daily at **6:00 PM ET** = 1 invocation/day
- Triggers ECS task for weight optimization
- Enabled: no flag, always on

**Why It's Wasteful:**
- Paper trading doesn't have real P&L to optimize weights
- Useful for monitoring but takes compute time
- 252 trading days/year × 1 task = 252 ECS task runs

**Fix:**
- If not actively testing weights: **disable in dev**
- Keep only 1-2x week for spot-checking
- Would need to remove/comment out resource in terraform

**Savings:** ~$0.50/month (negligible)

---

## 🟡 MEDIUM PRIORITY COST ISSUES

### 4. Provisioned Concurrency on API Lambda: $12/month

**Current State:**
- terraform.tfvars:64: `api_lambda_provisioned_concurrency = 1`
- Keeps 1 Lambda instance warm 24/7
- Cost: ~$12/month per unit

**Why Enabled:**
- Avoids 15-40s VPC cold start on API calls
- Without it: first request to /api/* returns 502 timeout

**Dev Trade-off:**
- In dev with low traffic: cold starts acceptable
- No SLA requirement
- Dashboard queries are infrequent

**Fix:**
```hcl
# In terraform.tfvars, set:
api_lambda_provisioned_concurrency = 0
```

**Savings:** $12/month  
**Trade-off:** Accept first API call may take 15-40s

---

### 5. Pre-warm Lambda Schedules: $0.01/month (Negligible)

**Current State:**
- terraform/modules/services/2x-daily-orchestrator.tf:269-370
- 3 pre-warm schedules (5 minutes before each trading run)
  - 9:25 AM ET (pre-warm for 9:30 AM run)
  - 12:55 PM ET (pre-warm for 1:00 PM run)
  - 2:55 PM ET (pre-warm for 3:00 PM run)
- Each is a dry-run Lambda invocation (no trades)
- Total: 3/day × 252 days = 756 invocations/year

**Why Enabled:**
- Prevents cold start on SLA-critical trades (3:00 PM must finish by 3:15 PM)
- Useful for production, not needed in dev

**Fix:**
- Set `enable_morning_orchestrator = false` to disable all (too aggressive)
- Or set `enable_afternoon_orchestrator = false` and `enable_preclose_orchestrator = false` to keep only 1 run

**Savings:** Negligible (~$0.01/month)

---

### 6. Multiple Daily Orchestrator Runs: $0.02/month (Negligible Cost, Useful for Testing)

**Current State:**
- 4 scheduled orchestrator runs (terraform/modules/services/2x-daily-orchestrator.tf):
  - 9:30 AM ET: Morning trading run [ENABLED]
  - 1:00 PM ET: Afternoon rebalance [ENABLED]
  - 3:00 PM ET: Pre-close trades [ENABLED]
  - 5:30 PM ET: Evening signal prep [ENABLED]
- Plus 5 pre-warm runs

**Lambda Costs:**
- 4 runs × 252 trading days = 1,008 invocations/year
- Plus RDS + network costs
- At ~$0.20 per 5-minute run: ~$0.35/month

**Why Enabled:**
- Testing multiple execution windows
- Useful for dev/staging
- Paper trading only (no real cost impact)

**Fix:**
- For cost: keep 1x daily (evening 5:30 PM only)
- For testing: keep all 4x (minimal cost)

**Recommendation:** Keep as-is (great for testing), negligible cost

---

## 🟢 ALREADY OPTIMIZED

### RDS Database: ~$32/month ✓
- `db.t4g.small`: $25-30/month
- 61 GB storage: $6-8/month
- Backup retention: 1 day (minimal)
- Single-AZ (no Multi-AZ cost)
- No customer-managed KMS (AWS-managed encryption)

**Status:** Good for dev. ✓

### S3 Storage: ~$2-3/month ✓
- No versioning (terraform.tfvars:122: `enable_s3_versioning = false`)
- Short lifecycle: 30 days code artifacts, 14 days data
- Intelligent tiering disabled

**Status:** Good for dev. ✓

### CloudWatch Logs: ~$2/month ✓
- 5-day retention for app logs
- 3-day retention for API Gateway logs
- Log archive transitions to Glacier after 90 days

**Status:** Good for dev. ✓

### ECS Fargate: On-demand, FARGATE_SPOT enabled ✓
- terraform/modules/loaders uses FARGATE_SPOT (80% discount)
- Data loaders only run on schedule
- No constantly-running containers

**Status:** Good. ✓

### CloudFront: Minimal for dev ✓
- terraform.tfvars:15: `cloudfront_enabled = true`
- Frontend distribution enabled
- Dev traffic only

**Status:** OK, negligible cost. ✓

---

## 📊 ESTIMATED MONTHLY BREAKDOWN

| Item | Cost | Notes |
|------|------|-------|
| RDS (instance + storage) | $32 | db.t4g.small + 61GB |
| NAT Gateway + data transfer | $35 | 🔴 BIGGEST WASTE |
| Lambda invocations | $5 | Orchestrator (4x/day) + monitor (6x/day) + pre-warm |
| Provisioned Concurrency | $12 | API Lambda keep-warm 🟡 |
| CloudWatch Logs | $2 | 5-day retention |
| S3 Storage | $2 | Logs, artifacts, frontend |
| CloudFront | $3 | Minimal dev traffic |
| DynamoDB (token blocklist) | $1 | On-demand, minimal |
| Secrets Manager | $0.40 | 2-3 secrets |
| **TOTAL** | **$92-95** | **Annual: ~$1,100** |

---

## 🎯 RECOMMENDED ACTIONS (Priority Order)

### Immediate (This Week)

1. **Disable Execution Monitor** (terraform.tfvars:81)
   ```hcl
   enable_execution_monitor = false
   ```
   **Saves:** $0.50/month + cleaner logs
   **Effort:** 1 line change
   **Risk:** None (dev only)

2. **Disable Weight Optimization** in terraform/modules/services/2x-daily-orchestrator.tf
   ```hcl
   # Comment out or delete:
   resource "aws_scheduler_schedule" "weight_optimization" { ... }
   ```
   **Saves:** $0.50/month
   **Effort:** Remove resource
   **Risk:** None (dev only)

3. **Reduce Provisioned Concurrency to 0** (terraform.tfvars:64)
   ```hcl
   api_lambda_provisioned_concurrency = 0
   ```
   **Saves:** $12/month
   **Effort:** 1 line change
   **Risk:** Accept 15-40s cold start on first API call (acceptable in dev)

### Medium Term (This Month)

4. **Remove NAT Gateway, Use Bastion Instead**
   - Modify terraform/modules/vpc/main.tf to disable NAT
   - Enable bastion host with auto-shutdown schedule
   - **Saves:** $32/month
   - **Effort:** Moderate (VPC + bastion config)
   - **Risk:** Need bastion for SSH tunnel to RDS
   - **Note:** Requires terraform/modules/compute update

5. **Clean Up Unnecessary Terraform State**
   - Check for orphaned resources (terraform state show)
   - Delete any unused modules
   - Example: Check if any VPC endpoints are dangling

### For Production Only (Don't Do in Dev)

- Keep provisioned concurrency (prevent 502 errors)
- Keep pre-warm schedules (meet SLAs)
- Keep execution monitor (verify trades executed)
- Keep multiple orchestrator runs (catch opportunities)
- Keep NAT gateway (external API calls)

---

## ⚠️ PERMISSION REQUEST CONTEXT

The user mentioned "someone is trying to give themselves the permissions to kill some tasks."

**This is a BAD IDEA if they mean:**
- Killing the RDS database (loses all data)
- Disabling all Lambdas (breaks orchestrator)
- Removing all networking (breaks everything)

**This makes sense if they mean:**
- ✅ Disabling execution monitor (low-value in dev)
- ✅ Removing provisioned concurrency (acceptable cold starts)
- ✅ Removing NAT gateway (use bastion instead)
- ✅ Disabling pre-warm schedules (low-value in dev)

**DO NOT grant blanket "kill" permissions.** Instead:
1. Request specific resource deletions with business justification
2. Have code review before Terraform changes
3. Test in staging first
4. Use cost explorer to verify savings

---

## 🔧 NEXT STEPS

1. **Run AWS Cost Explorer** to validate estimated costs
   - AWS Console → Cost Management → Cost Explorer
   - Filter by service: RDS, Lambda, NAT Gateway, CloudWatch Logs
   - Compare year-over-year or month-over-month

2. **Review Terraform tfvars** (already analyzed above)

3. **Apply immediate fixes** (disable monitor + optimize concurrency)

4. **Plan NAT removal** (biggest savings)

5. **Monitor for unused resources** (orphaned ECS clusters, unused S3 buckets, etc.)

---

## 📝 Questions for Team

1. Are all 4 daily orchestrator runs actually needed for testing? (Cost: negligible, but adds operational complexity)
2. Why is provisioned concurrency set to 1? Is the 502 error happening frequently?
3. Is the NAT gateway used for anything other than Lambda internet access?
4. Are there any VPC endpoints already enabled? (Check terraform/modules/vpc/main.tf)
5. Do you have AWS Cost Anomaly Detection enabled? (Set alerts for spikes)

---

**Cost Audit Complete.** Estimated savings with all recommendations: **$45-50/month** (~$540-600/year).
