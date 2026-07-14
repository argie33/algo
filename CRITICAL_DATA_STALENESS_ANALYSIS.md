# CRITICAL: AWS Data Staleness - Root Cause Analysis

**Date:** 2026-07-14  
**Severity:** CRITICAL - Production dashboard showing 14-day-old metrics  
**Status:** INVESTIGATING  

## Problem Statement

AWS Lambda /api/algo/scores is returning NULL growth scores with 2026-06-30 timestamps (14 days old), while local dev shows fresh data (same day). The composite scores ARE present but growth scores are missing, making the scores panel incomplete.

## Data Comparison

| Metric | AWS Lambda | Local Dev | Status |
|--------|-----------|-----------|--------|
| Composite Score | 79.31 | 79.31 | ✓ MATCH |
| Growth Score | **NULL** | ~0.39 | ✗ DIVERGE |
| RS Percentile | **0.0** | ~53 | ✗ DIVERGE |
| Last Updated | 2026-06-30 | 2026-07-14 | ✗ 14 days old |

## Root Cause Investigation

### Why LOCAL dev is fresh:
```
LOCAL Orchestrator (dev machine):
  - /algo-orchestrator/ runs locally via script (python scripts/run_local_orchestrator.py)
  - Invokes Phase 1, Phase 2, ... Phase 9 sequentially
  - Phase 7/8/9 calculate growth scores and update stock_scores table
  - Successfully running today: 12 execution runs (all succeeded)
  - Data written to LOCAL PostgreSQL database
```

### Why AWS is stale:
```
AWS Orchestrator (production):
  - Supposed to run via EventBridge Scheduler (MON-FRI 2AM/4:05PM ET)
  - Invokes Step Functions state machine (algo-eod-pipeline)
  - Step Functions calls Lambda task runner for each phase
  - Growth score calculation phase (Phase 7/8/9) hasn't run since Jun 30
  - RDS stock_scores table has composite scores but NULL growth scores
```

## Hypothesis: EventBridge/Step Functions Not Running Growth Calculation

### Possibility 1: EventBridge Scheduler Not Triggering
- **Check:** AWS EventBridge Scheduler - verify "algo-pipeline-dev" rules are enabled and firing
- **Expected:** Rules should fire at 2:00 AM ET and 4:05 PM ET every weekday
- **Evidence:** No growth score updates since Jun 30 suggests scheduler stopped firing

### Possibility 2: Step Functions Not Executing Growth Phase
- **Check:** Step Functions execution history - look for halts/errors in Phase 7/8/9
- **Expected:** Phase 7 (quality metrics) and Phase 9 (growth score recalculation) should complete
- **Evidence:** Need CloudWatch logs for Phase status

### Possibility 3: Growth Score Lambda Failed/Changed
- **Check:** Lambda function code - verify growth score calculation logic unchanged
- **Check:** RDS IAM permissions - verify Lambda can write to stock_scores
- **Evidence:** Composite scores ARE calculated, so database connection works; suggests growth calculation failed

### Possibility 4: Data Backlog - Growth Calculation Waiting on Other Phase
- **Check:** Phase dependencies - Phase 9 depends on Phase 1, 2, 3, 4, 5, 6
- **Expected:** If Phase 1-6 halt, Phase 9 won't run
- **Evidence:** Check if EOD price loading is blocking growth calculation

## Investigation Checklist

### Immediate Actions (This Session)
- [ ] Push all pending commits to trigger AWS deployment
- [ ] Check GitHub Actions CI/CD deployment status
- [ ] Verify Lambda functions deployed successfully
- [ ] Run manual health check against AWS API

### Next Session Actions (AWS-Specific Diagnostics)
- [ ] Check EventBridge Scheduler rules in AWS console (Enable if disabled)
- [ ] Check Step Functions execution history for recent runs
- [ ] Review CloudWatch Logs for Phase 7/8/9 failures
- [ ] Check RDS Lambda IAM permissions (stock_scores table write)
- [ ] Trigger manual orchestrator run via Lambda: `trigger-orchestrator` with `--run all`

### Escalation if Needed
- [ ] Contact AWS support if scheduler/Step Functions appears broken
- [ ] Check AWS service health dashboard for outages
- [ ] Review Terraform config for EventBridge/Step Functions setup

## Impact

- **Dashboard Effect:** Scores panel shows complete data locally but incomplete in AWS
- **Risk Assessment:** Users in AWS environment see stale metrics for trading decisions
- **Workaround:** Use local development mode for accurate growth score data

## Files to Review

- `steering/OPERATIONS.md` - EventBridge scheduler configuration
- `steering/DATA_LOADERS.md` - Loader execution and dependencies
- `terraform/modules/services/2x-daily-orchestrator.tf` - EventBridge rules
- `lambda/algo_orchestrator/lambda_function.py` - Orchestrator phases

---

**Next Update:** After GitHub Actions deployment completes and AWS systems verified.
