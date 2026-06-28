# IMMEDIATE ACTION REQUIRED - Dashboard Data Refresh

## Current Status (2026-06-28)
Dashboard shows critical data issues:
- quarterly_income_statement: **STALE 6.3 days** (last update 2026-06-22)
- quarterly_cash_flow: **STALE 6.3 days** (last update 2026-06-22)
- aaii_sentiment: **STALE 6.5 days** (last update 2026-06-22, WAF-blocked)
- earnings_calendar: **EMPTY** (0 records, DNS issue in local env only)

## Root Cause & Fix Status

### Issue 1: Quarterly Loaders (CRITICAL)
**Problem**: Watermark manager parsing bug
**Status**: ✅ FIXED (commit 6f3f377ee) - **READY FOR DEPLOYMENT**
**What changed**: `utils/watermark_manager.py` now handles fiscal_year integers (2026 format)

**Action Required**: 
1. User with admin AWS access run:
   ```bash
   cd terraform
   terraform apply -auto-approve
   ```
   Takes ~5 minutes

2. Then immediately trigger loaders:
   ```bash
   # Get network config
   SUBNET=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=algo-private-subnet" --query 'Subnets[0].SubnetId' --output text)
   SG=$(aws ec2 describe-security-groups --filters "Name=tag:Name,Values=algo-ecs-tasks" --query 'SecurityGroups[0].GroupId' --output text)
   
   # Trigger quarterly income loader
   aws ecs run-task \
     --cluster algo-cluster \
     --task-definition algo-financials_quarterly_income-loader \
     --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG]}"
   
   # Trigger quarterly cash flow loader
   aws ecs run-task \
     --cluster algo-cluster \
     --task-definition algo-financials_quarterly_cashflow-loader \
     --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG]}"
   ```

3. Monitor logs (should complete in 60-90 minutes):
   ```bash
   aws logs tail /ecs/algo-financials_quarterly_income-loader --follow
   aws logs tail /ecs/algo-financials_quarterly_cashflow-loader --follow
   ```

**Expected Result**: 
- Dashboard will show quarterly data updated to 2026-06-29
- 5,168 income records refreshed
- 5,311 cash flow records refreshed

---

### Issue 2: AAII Sentiment (LOW PRIORITY)
**Problem**: Imperva WAF returns 403 Forbidden
**Status**: ❌ NOT FIXABLE without external changes
**Options**:
1. Contact AAII to whitelist algo-developer IP
2. Use HTTP proxy (requires vendor account)
3. Implement Playwright browser automation (performance cost)
4. Accept missing AAII data (data is optional, falls back gracefully)

**Action**: None required - data is optional. Dashboard continues without it.

---

### Issue 3: Earnings Calendar (NO ACTION NEEDED)
**Problem**: Shows EMPTY in local testing
**Status**: ✅ Works in AWS (DNS issue is local-only)
**Action**: None - will populate automatically when loaders run in AWS

---

## Priority Actions (In Order)

### 🔴 CRITICAL - Do Now
```bash
cd terraform
terraform apply -auto-approve
```
**Time**: 5 minutes
**Fixes**: quarterly_income_statement + quarterly_cash_flow stale data

### 🟠 HIGH - Do After Terraform (optional, for immediate data)
```bash
# Manually trigger loaders to start immediately
# (otherwise they run on schedule: Monday 1:00 AM and 3:00 AM ET)
```
**Time**: 60-90 minutes for loaders to complete
**Fixes**: Dashboard data refreshes immediately instead of waiting until Monday

### 🟡 MEDIUM - Next Sprint
- Implement AAII sentiment browser automation (Playwright)
- Add CloudWatch alarms for loader failures

---

## What's Already Done
- ✅ Watermark bug identified and fixed
- ✅ Fix tested locally with quarterly_income_statement and quarterly_cash_flow
- ✅ Fix committed to git main (6f3f377ee)
- ✅ All documentation complete
- ✅ Deployment scripts ready

## Risk Assessment
- **Watermark fix**: Very low risk (isolated date parsing logic, backward compatible)
- **Deployment**: Standard terraform apply (no breaking changes)
- **Rollback**: Simple (revert task definition to previous revision)

## Success Criteria
After completing the critical action above:
- Dashboard quarterly_income_statement shows current date (not 2026-06-22)
- Dashboard quarterly_cash_flow shows current date (not 2026-06-22)
- Both show record counts > 5,000
- Green status indicator in health panel

---

## Code Verification
The fix is minimal and safe:
```python
# Before: Only parsed dates
return date.fromisoformat(str(value).split("T")[0])

# After: Handles years AND dates
str_val = str(value).strip()
if len(str_val) == 4 and str_val.isdigit():
    year = int(str_val)
    if 1990 < year < 2100:
        return date(year, 1, 1)
return date.fromisoformat(str_val.split("T")[0])
```

This allows fiscal_year=2026 to be parsed as date(2026, 1, 1), enabling proper watermark comparison.
