# Session 23 - Critical Blockers Requiring Immediate Fixes

**Status:** Comprehensive system audit identified 5 critical/high-priority issues. 1 SECURITY fix applied. 4 issues require urgent attention for production deployment.

---

## ✅ FIXED - Security: SMTP Password Exposure

**Issue:** ALERT_SMTP_PASSWORD exposed in Lambda environment variables
**Root Cause:** Credentials visible to anyone with lambda:GetFunction permission; stored in CloudWatch logs
**Fix Applied:** Moved to AWS Secrets Manager with secure IAM policy
**Impact:** Eliminates credential exposure vulnerability
**Commit:** ed3933ab5

---

## 🔴 CRITICAL - Data Integrity: Position/Trade Sync Broken

**Issue:** 3 open positions (NTCT, WABC, HTGC) exist without corresponding trade records in algo_trades
**Root Cause:** algo_trades table schema missing position_id foreign key column
**Impact:** Portfolio reconciliation broken, entry prices not verified, performance attribution impossible
**Symptoms:**
- Positions can exist without trade history
- Cannot reconstruct position cost basis
- Risk calculations unreliable (don't match trades)
- Phase 9 reconciliation fails to match positions to trades

**Database Schema Problem:**
```sql
-- algo_positions has: position_id (PK), symbol, quantity, status, ...
-- algo_trades has: id, trade_id, symbol, entry_price, status, ...
-- MISSING: no foreign key linking positions to trades
```

**Fix Required:**
1. Add `position_id` column to algo_trades table
2. Add foreign key constraint: `FOREIGN KEY (position_id) REFERENCES algo_positions(position_id)`
3. Reconcile existing trades with positions via symbol + date matching
4. Add constraint validation in entry_handler.py before inserting trades

**Priority:** CRITICAL - Blocks reconciliation logic
**Estimated Fix Time:** 2-3 hours (schema migration + reconciliation logic)

---

## 🟠 HIGH - Infrastructure: Developer IAM Permissions Missing

**Issue:** algo-developer user lacks permissions needed for production troubleshooting
**Missing Permissions:**
- `dynamodb:GetItem`, `dynamodb:Query`, `dynamodb:Scan` → Cannot inspect orchestrator_locks table
- `events:DescribeRule`, `events:ListTargets`, `events:ListRules` → Cannot verify EventBridge scheduler configuration
- `logs:GetLogEvents`, `logs:FilterLogEvents` → Cannot access detailed Lambda logs for debugging

**Impact:**
- Developer cannot diagnose lock contention during orchestrator failures
- Cannot verify EventBridge rules are firing correctly
- Cannot access full logs for incident response
- Blocks production troubleshooting

**Fix Required:**
```hcl
# Add to terraform/modules/iam/main.tf in data.aws_iam_policy_document.developer
{
  Effect = "Allow"
  Action = [
    "dynamodb:GetItem",
    "dynamodb:Query",
    "dynamodb:Scan",
    "dynamodb:GetRecords"
  ]
  Resource = [
    "arn:aws:dynamodb:*:*:table/algo-orchestrator-locks-*",
    "arn:aws:dynamodb:*:*:table/algo-loader-locks-*"
  ]
}
{
  Effect = "Allow"
  Action = [
    "events:DescribeRule",
    "events:ListTargets",
    "events:ListRules"
  ]
  Resource = "arn:aws:events:*:*:rule/algo-*"
}
{
  Effect = "Allow"
  Action = [
    "logs:GetLogEvents",
    "logs:FilterLogEvents",
    "logs:GetLogGroupName"
  ]
  Resource = "arn:aws:logs:*:*:*"
}
```

**Priority:** HIGH - Blocks production incident response
**Estimated Fix Time:** 30 minutes (IAM policy addition)

---

## 🟠 HIGH - Data Pipeline: Auxiliary Loaders Not Executing

**Issue:** 21 critical loaders stale 7+ days (buy_sell_daily 19d, sector_ranking 22d, algo_metrics_daily 45d)
**Root Cause:** Auxiliary loaders (low priority) not included in Step Function state machine execution
**Pattern:** Critical loaders (price, technical, stock_scores, metrics) are current; auxiliary loaders are stale

**Affected Loaders:**
- buy_sell_daily (19d old) - CRITICAL for signal generation
- buy_sell_weekly (19d old)
- buy_sell_monthly (19d old)
- sector_ranking (22d old) - Used for sector momentum
- industry_ranking (36d old) - Used for industry selection
- algo_metrics_daily (45d old) - Dashboard metrics

**Likely Root Cause:**
Step Function state machine (`.github/workflows/deploy-ecs-image.yml` or loader pipeline in `terraform/modules/pipeline`) does not include auxiliary loader tasks in state definition.

**Fix Required:**
1. Check Step Function state machine JSON definition
2. Verify all loader tasks are included (both critical and auxiliary)
3. If auxiliary tasks missing: Add them to state machine definition
4. If EventBridge schedule wrong: Verify loader trigger in `terraform/modules/loaders/main.tf` includes auxiliary loaders
5. Manually trigger one auxiliary loader to verify execution:
```bash
python3 loaders/load_buy_sell_daily.py
```

**Verification:**
```sql
SELECT table_name, age_days FROM data_loader_status 
WHERE age_days > 7 
ORDER BY age_days DESC;
```

**Priority:** HIGH - Blocks historical analysis and sector-based trading
**Estimated Fix Time:** 1-2 hours (state machine investigation + configuration fix)

---

## Summary of Critical Work

| Issue | Severity | Status | Est. Time | Blocking |
|-------|----------|--------|-----------|----------|
| SMTP password exposure | CRITICAL | ✅ FIXED | - | No |
| Position/trade sync | CRITICAL | ⏳ TODO | 2-3h | YES |
| Developer IAM perms | HIGH | ⏳ TODO | 30m | NO* |
| Auxiliary loaders | HIGH | ⏳ TODO | 1-2h | YES |

*Blocks troubleshooting but not immediate trading execution

---

## Recommended Action Plan

1. **Immediate (Today):** 
   - Fix position/trade schema (database migration)
   - Add developer IAM permissions (small TF change)
   
2. **Follow-up (Tomorrow):**
   - Investigate and fix auxiliary loader execution
   - Test full end-to-end with correct loader data

3. **Verification:**
   - Run full orchestrator execution
   - Verify all 21 loaders have current data
   - Test position entry and reconciliation

---

**Next Session:** Once these 4 issues are fixed, system will be fully production-ready.
