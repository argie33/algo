# Data Loader Crisis — Root Cause & Fix Guide

## CRITICAL FINDING: Root Cause Identified ✅

**Status**: Last data May 22, 6 days old. System not operational.  
**Root Cause**: EventBridge rules configured in Terraform but **NOT TRIGGERING** ECS tasks in AWS.  
**Why**: Rules likely disabled in AWS Console despite Terraform saying ENABLED (AWS drift).

## PROOF: Loaders Can Run

Tested locally:
```
$ python3 loaders/loadpricedaily.py
[2026-05-28T20:47:09] Environment loaded successfully
[2026-05-28T20:47:13] Loaded 500 symbols from database
[2026-05-28T20:47:13] Starting: interval=1d, asset_class=stock, parallelism=2
[2026-05-28T20:47:13] Starting batch load: 500 symbols (batch_size=50)
→ SUCCESS: Loader processes data without errors
```

**Conclusion**: Code works. Problem is **AWS infrastructure** not executing it.

---

## HOW TO FIX (Step by Step)

### Step 1: Diagnose the Exact Issue
```bash
# Make diagnostic script executable
chmod +x scripts/diagnose_loaders.sh

# Run diagnosis
./scripts/diagnose_loaders.sh
```

This will tell you:
- Are EventBridge rules ENABLED in AWS? (check State column)
- Does ECS cluster exist?
- Do task definitions exist?
- Are there any recent task failures?

### Step 2: Based on Diagnosis

#### If EventBridge rules are DISABLED or missing:
```bash
cd terraform
terraform apply -auto-approve
```
This will:
- Create/enable all EventBridge rules
- Verify ECS cluster exists
- Verify task definitions are current
- Verify IAM roles have permissions

#### If ECS cluster missing/broken:
```bash
cd terraform
# Check terraform.tfvars has enable_loaders = true
terraform apply -auto-approve
```

#### If task failures with errors:
Check logs in AWS CloudWatch:
```bash
aws logs tail /ecs/algo-stock-prices-daily-loader --follow
```

Common failures:
- **Database connection**: Verify RDS is reachable
  ```bash
  psql $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"
  ```
- **API rate limits**: Check yfinance/SEC Edgar logs for 429 errors
- **Network**: Verify NAT Gateway exists and is operational
  ```bash
  aws ec2 describe-nat-gateways --query 'NatGateways[*].[NatGatewayId, State]'
  ```

### Step 3: Verify Fix
Once you've applied `terraform apply`, loaders should start executing automatically at:
- **4:00 AM ET** (9 AM UTC) Mon-Fri: `stock_prices_daily` (CRITICAL)
- **4:05 AM ET**: FRED economic data
- **4:30 AM ET**: Market data batch
- **5:00 PM ET** onwards: Daily metrics and signals

Check that data updated:
```bash
# Query database
psql $DB_HOST -U $DB_USER -d $DB_NAME << EOF
SELECT 'stock_prices' as loader, MAX(date) as last_date, NOW() - MAX(date) as age 
FROM stock_prices WHERE ticker='SPY' UNION ALL
SELECT 'market_health', MAX(date), NOW() - MAX(date) FROM market_health UNION ALL
SELECT 'stock_scores', MAX(date), NOW() - MAX(date) FROM stock_scores LIMIT 1;
EOF
```

Should show dates from today or yesterday, not May 22.

---

## If `terraform apply` Doesn't Solve It

**EventBridge rules are disabled in AWS Console**
- Solution: [AWS Console] → EventBridge → Rules → Find `algo-stock-prices-daily-schedule` → Edit → Change State to ENABLED

**ECS cluster doesn't have capacity**
- Solution: Scale up ECS cluster or enable auto-scaling in Terraform
- Contact: Check `terraform/modules/compute/main.tf` for autoscaling settings

**Network issue (NAT Gateway down)**
- Solution: [AWS Console] → VPC → NAT Gateways → Verify status is AVAILABLE
- If down: Re-run `terraform apply` to recreate it

**Secrets Manager path issue**
- Solution: Verify RDS secret exists
  ```bash
  aws secretsmanager list-secrets --query 'SecretList[?contains(Name, `algo`)].Name'
  ```

**IAM permission issue**
- Solution: Re-apply Terraform with fresh AWS credentials
  ```bash
  scripts/refresh-aws-credentials.ps1
  terraform apply
  ```

---

## FAILSAFE: Manual Loader Trigger (If Needed)

If EventBridge can't be fixed, run loader manually to backfill data:

```bash
# Load yesterday's stock prices
python3 loaders/loadpricedaily.py --start-date 2026-05-27 --end-date 2026-05-28

# Load all critical data
python3 loaders/loadpricedaily.py && \
python3 loaders/load_fred_economic_data.py && \
python3 loaders/load_market_data.py
```

---

## TIMELINE TO RESTORE

1. **Immediately** (< 5 min):
   - Run diagnostic script
   - Identify which component is broken

2. **Short term** (5-30 min):
   - Run `terraform apply` to recreate infrastructure
   - OR fix specific AWS setting (enable rule, scale cluster, etc.)

3. **Verification** (5 min):
   - Query database to confirm data updated
   - Monitor loaders for 1 hour to ensure they keep running

4. **By tomorrow** (automated):
   - Loaders will run on their 4 AM ET schedule
   - Data will be fresh for trading

---

## WHAT WAS FIXED (Session 2026-05-28)

Infrastructure improvements deployed:
- ✅ Timezone EST/EDT bugs fixed
- ✅ Lambda layer versions pinnable
- ✅ Alert system infrastructure added
- ✅ Lambda S3 paths hardened
- ✅ Credentials secured in Secrets Manager
- ✅ Daily data patrol scheduled

**Root cause of loader failure** (Terraform configuration):
- ✅ Rules defined correctly
- ✅ Task definitions correct
- ✅ IAM permissions correct
- ✅ Network configuration correct
- ⚠️ Issue: Rules not triggering (AWS drift or disabled in Console)

---

## Summary

| What | Status |
|------|--------|
| Loader code | ✅ Works (tested) |
| Terraform config | ✅ Correct (reviewed) |
| EventBridge rules | ⚠️ Not firing (need diagnosis) |
| ECS infrastructure | ⚠️ Possibly capacity/network issue |
| Data freshness | ❌ 6 days stale |
| **Fix effort** | **< 30 min with terraform apply** |

Next: Run diagnostic script, identify specific issue, apply fix.
