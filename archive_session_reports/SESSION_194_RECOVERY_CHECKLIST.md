# SESSION 194 CRITICAL RECOVERY CHECKLIST

**Status:** Recovery in progress  
**Last Updated:** 2026-07-16 21:58 UTC  
**Triggered:** Commit 919daf3 pushed to trigger GitHub Actions Lambda deployment

## Three Critical Blockers

```
BLOCKER #3 (Root Cause)     BLOCKER #2 (Blocked By #3)    BLOCKER #1 (Visible)
├─ Market exposure 2d stale ├─ ValueMetrics 6d stale     ├─ Phase 8 credentials error
│  (should be TODAY)        │  (blocked from running)     │  (Lambda code not updated)
│  EOD pipeline             │  Computed metrics pipeline  │  Session 193 fix not deployed
│  hasn't updated it        │  waiting for #3 to fix      │  
└─ Must fix FIRST          └─ Will fix after #3         └─ Will fix FIRST
```

## Recovery Sequence

### PHASE 1: Deploy Lambda Credentials Fix (5-15 minutes)
**Status:** ⏳ IN PROGRESS

**What we did:**
- Commit 919daf3 pushed to trigger GitHub Actions
- GitHub Actions will redeploy Lambda with Commit 4c37440f5 (credentials fix)

**Deployment Timeline:**
- T+0m: Push detected by GitHub Actions
- T+1-5m: Build & test Lambda
- T+5-10m: Deploy to AWS
- T+10-15m: Lambda container updated

**To Monitor (Manual Check):**
```bash
# Check if Lambda code was updated (only works in Lambda)
# You'll see this in CloudWatch logs:
# "[CREDENTIALS] Found credentials in algo-algo-secrets-dev"
```

**To Verify Once Lambda Updates:**
```bash
# This will trigger orchestrator with fresh Lambda code
python3 scripts/trigger_morning_pipeline.py

# Check logs for credentials line (should appear ~5-15 min after push)
# Expected output in Phase 8: "[CREDENTIALS] Found credentials in algo-algo-secrets-dev"

# Also check orchestrator database
sqlite3 :memory: <<'EOF'
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()
cur.execute('''
    SELECT started_at, overall_status, halt_reason
    FROM algo_orchestrator_runs
    WHERE started_at > NOW() - INTERVAL '15 minutes'
    ORDER BY started_at DESC LIMIT 1
''')
row = cur.fetchone()
if row:
    started, status, halt = row
    print(f"Latest run: {started} - {status}")
    if halt:
        print(f"Halt: {halt[:100]}")
    else:
        print("SUCCESS - No halt!")
EOF
```

**Success Criteria:**
- ✓ Orchestrator run completes without credentials error
- ✓ Phase 8 executes (trades attempted)
- ✓ No "[PHASE 8 CRITICAL] Alpaca credentials" in halt_reason

**Estimated Completion:** 2026-07-16 22:15 UTC (if push detected immediately)

---

### PHASE 2: Fix Market Exposure Table (Upstream Dependency)
**Status:** ⏳ PENDING PHASE 1
**Estimated Time:** 30 min

**Why This Matters:**
- Value metrics pipeline checks if market_exposure_daily is fresh
- If it's 2+ days old, orchestrator HALTS before pipeline can run
- Cannot refresh value_metrics until market_exposure_daily is fresh

**Investigation:**
```bash
# Check market_exposure_daily status
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

cur.execute('SELECT MAX(report_date), COUNT(*) FROM market_exposure_daily')
latest, count = cur.fetchone()
today = datetime.now().date()
if latest:
    age = (today - latest).days
    print(f"market_exposure_daily: {latest} ({age}d old) - {count} rows")
    if age > 1:
        print("STALE - EOD pipeline must run to refresh")
else:
    print("NO DATA")

conn.close()
EOF
```

**Action:**
```bash
# Trigger EOD pipeline to recalculate market_exposure_daily
# This runs Phase 7 (risk metrics including market exposure)
python3 scripts/trigger_eod_pipeline.py

# This will:
# 1. Load data from earlier phases
# 2. Calculate market exposure in Phase 7
# 3. Update market_exposure_daily table
# 4. Complete without phase 8 (no trades at EOD)

# Wait ~30 min for completion
# Then check:
sqlite3 :memory: <<'EOF'
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()
cur.execute('SELECT MAX(report_date) FROM market_exposure_daily')
latest = cur.fetchone()[0]
print(f"market_exposure_daily latest: {latest} (should be TODAY)")
conn.close()
EOF
```

**Success Criteria:**
- ✓ market_exposure_daily updated to TODAY (2026-07-16)
- ✓ Count > 0 (has data)
- ✓ EOD orchestrator run shows status "success"

**Estimated Completion:** 2026-07-16 22:45 UTC

---

### PHASE 3: Refresh ValueMetrics (Final Fix)
**Status:** ⏳ PENDING PHASE 2
**Estimated Time:** 2 hours

**Why This Matters:**
- value_metrics is 6 days stale (2026-07-10)
- Depends on market_exposure_daily being fresh (just fixed in Phase 2)
- Factor score coverage needs 80%+ (currently 78.5%)
- ECS task resources already increased (Commit 90291b160)

**Action:**
```bash
# After Phase 2 completes, trigger Computed Metrics Pipeline
# This runs the ValueMetrics ECS task with increased resources
python3 scripts/trigger_computed_metrics_pipeline.py

# Wait ~2 hours for ECS task to complete
# Monitor progress:
aws logs tail /aws/ecs/algo-value_metrics --follow

# Expected logs:
# "Processing 4711 stocks..."
# "Batch 1/X: Computing metrics..."
# "Successfully updated value_metrics table"
```

**Verify Completion:**
```bash
# Check if value_metrics was refreshed to today
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

# Check value_metrics freshness
cur.execute('SELECT MAX(date), COUNT(*) FROM value_metrics')
latest, count = cur.fetchone()
today = datetime.now().date()
if latest:
    age = (today - latest).days
    print(f"value_metrics: {latest} ({age}d old) - {count} rows")
else:
    print("NO DATA")

# Check factor score coverage
cur.execute('''
    SELECT COUNT(*) as total,
           SUM(CASE WHEN factor_score IS NOT NULL THEN 1 ELSE 0 END) as present,
           ROUND(100.0 * SUM(CASE WHEN factor_score IS NOT NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0))::int as coverage_pct
    FROM algo_scores
    WHERE score_date = CURRENT_DATE
''')
total, present, coverage = cur.fetchone()
print(f"Factor scores: {coverage}% coverage ({present}/{total})")
print(f"Target: >=80%")

conn.close()
EOF
```

**Success Criteria:**
- ✓ value_metrics updated to TODAY (2026-07-16)
- ✓ positioning_metrics updated to TODAY
- ✓ Factor score coverage >= 80%
- ✓ No stocks marked data_unavailable (all have >50% metrics)

**Estimated Completion:** 2026-07-17 00:45 UTC

---

### PHASE 4: Verify Production Ready (Final Check)
**Status:** ⏳ PENDING PHASE 3

**Verification Script:**
```bash
python3 << 'EOF'
import psycopg2
from datetime import datetime

conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

print("=== PRODUCTION READINESS VERIFICATION ===\n")

# 1. Check all critical tables are fresh
tables = {
    'price_daily': 'date',
    'technical_data_daily': 'date',
    'value_metrics': 'date',
    'positioning_metrics': 'date',
    'market_exposure_daily': 'report_date',
}

today = datetime.now().date()
all_fresh = True
for table, date_col in tables.items():
    cur.execute(f"SELECT MAX({date_col}) FROM {table}")
    latest = cur.fetchone()[0]
    if latest:
        age = (today - latest).days
        status = "FRESH" if age == 0 else f"STALE ({age}d)"
        print(f"  {table:30} | {status}")
        if age > 1:
            all_fresh = False
    else:
        print(f"  {table:30} | NO DATA")
        all_fresh = False

# 2. Check orchestrator is running without halts
cur.execute('''
    SELECT COUNT(*) as success, COUNT(*) FILTER (WHERE overall_status = 'halted') as halts
    FROM algo_orchestrator_runs
    WHERE started_at > NOW() - INTERVAL '6 hours'
''')
success, halts = cur.fetchone()
print(f"\n  Orchestrator: {success} runs, {halts} halts (last 6h)")

# 3. Check factor score coverage
cur.execute('''
    SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE factor_score IS NOT NULL) / NULLIF(COUNT(*), 0))::int
    FROM algo_scores
    WHERE score_date = CURRENT_DATE
''')
coverage = cur.fetchone()[0]
print(f"  Factor scores: {coverage}% coverage (target: >=80%)")

# 4. Summary
print(f"\n  Overall: {'PRODUCTION READY' if all_fresh and coverage >= 80 else 'NEEDS WORK'}")

conn.close()
EOF
```

**Success Criteria:**
- ✓ All critical tables FRESH (today's date)
- ✓ Factor score coverage >= 80%
- ✓ Zero orchestrator halts in last 6 hours
- ✓ System ready for LIVE TRADING

---

## Monitoring Timeline

| Time | Action | Expected Result |
|------|--------|-----------------|
| Now | Commit 919daf3 pushed | GitHub Actions triggered |
| +5-10 min | Lambda deployed | New code running in AWS |
| +10-20 min | Trigger morning pipeline | Phase 8 uses credentials |
| +25 min | Market exposure fix begins | EOD pipeline runs |
| +55 min | Market exposure fresh | market_exposure_daily updated |
| +60 min | Trigger value_metrics | ECS task starts with 2x resources |
| +2h 10m | Value metrics complete | value_metrics refreshed to today |
| +2h 15m | Verify coverage | Factor scores >= 80% |

---

## Rollback Plan (If Something Goes Wrong)

If any phase fails:

```bash
# 1. Check CloudWatch logs
aws logs tail /aws/lambda/algo-orchestrator --follow
aws logs tail /aws/ecs/algo-value_metrics --follow

# 2. Check database for error details
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()
cur.execute('''
    SELECT started_at, halt_reason
    FROM algo_orchestrator_runs
    WHERE started_at > NOW() - INTERVAL '1 hour'
    ORDER BY started_at DESC LIMIT 3
''')
for started, halt in cur.fetchall():
    print(f"{started}: {halt}")
conn.close()
EOF

# 3. If Lambda has issues: revert to previous version
#    GitHub Actions keeps previous Lambda versions
#    Use AWS Lambda console to roll back

# 4. If Terraform has issues: check terraform state
#    Terraform changes only affect ECS task definitions
#    Should not affect Lambda or database
```

---

## Key Files Modified

| File | Commit | Change |
|------|--------|--------|
| lambda/algo_orchestrator/lambda_function.py | 4c37440f5 | Added algo-algo-secrets-dev fallback |
| config/credential_manager.py | 4c37440f5 | Same fallback logic |
| terraform/modules/loaders/main.tf | 90291b160 | ECS task resources: cpu 512→1024, memory 1024→2048 |
| CLAUDE.md | df53fb2d6 | Status updates |
| SESSION_194_RECOVERY_CHECKLIST.md | THIS SESSION | Recovery playbook |

---

## Current Understanding

**What Works:**
- Price data is FRESH (updated today)
- Lambda code fixes are committed and ready
- ECS task resources are increased
- Credentials exist in AWS Secrets Manager (algo-algo-secrets-dev)

**What's Broken:**
- Lambda running old code (doesn't know about algo-algo-secrets-dev)
- Market exposure calculation hasn't run since 2026-07-14
- Value metrics hasn't run since 2026-07-10
- Orchestrator blocked by stale dependencies

**Why This Happened:**
- GitHub Actions deployment of Commit 4c37440f5 may have failed
- EOD pipeline failed on 2026-07-15 (didn't update market_exposure_daily)
- Computed Metrics pipeline blocked waiting for fresh market exposure

**Solution Approach:**
- Force Lambda redeploy with latest code
- Manually trigger EOD pipeline to fix upstream dependency
- Manually trigger Computed Metrics pipeline with increased resources
- Monitor and verify at each step

---

## Next Command to Run

Once Phase 1 is complete (~15 min from now), run:

```bash
# Phase 1 verification - trigger orchestrator with new Lambda code
python3 scripts/trigger_morning_pipeline.py

# If successful (no credentials error), proceed to Phase 2
# If failed, check CloudWatch logs for root cause
```

**Important:** Do NOT proceed to Phase 2 until Phase 1 credentials are confirmed working!

---

## Questions & Troubleshooting

**Q: How do I know when Lambda is updated?**  
A: Check CloudWatch logs after running trigger_morning_pipeline.py. Should see "[CREDENTIALS] Found credentials in algo-algo-secrets-dev" in Phase 1.

**Q: Can I trigger all three phases at once?**  
A: NO! They have dependencies:
- Phase 1 (Lambda) must complete FIRST
- Phase 2 (market exposure) must complete BEFORE Phase 3 (value metrics)
- Running out of order will just fail again

**Q: What if market_exposure_daily is still stale after Phase 2?**  
A: Run EOD pipeline again. If it fails, check CloudWatch logs for error details.

**Q: Is live trading enabled during recovery?**  
A: NO! Orchestrator runs will halt until all critical tables are fresh. This is by design - prevent trading with stale data.

---

Created: 2026-07-16 21:58 UTC  
Session: 194 (Recovery)  
Status: Recovery in progress
