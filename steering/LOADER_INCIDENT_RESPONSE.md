---
title: Loader Incident Response & Prevention
---

# Critical Incident: EventBridge Loader Rules Not Deployed

**Incident Date:** 2026-07-04  
**Discovery Time:** 12:06 PM ET (Saturday noon)  
**Resolution Time:** 5:23 PM ET (Terraform deploy successful)  
**Status:** RESOLVED + PERMANENT FIX DEPLOYED

## Timeline

### 2026-06-28 → 2026-07-03: Infrastructure Gap
- EventBridge loader rules configured in Terraform code (correct)
- Deployment workflow 28711117488 FAILED (Lambda build error)
- Terraform apply never executed
- EventBridge rules never created in AWS
- Loader infrastructure incomplete but undetected

### 2026-07-03 Friday: Silent Failure
- 2:15 AM ET: stock_prices_daily **did NOT run** (no EventBridge rule)
- 2:55 AM ET: technical_data_daily **did NOT run**
- 3:15 AM ET: swing_trader_scores **did NOT run**
- 4:05 PM ET: EOD pipeline **did NOT run**
- Data became stale silently (no alert that loaders were skipped)

### 2026-07-04 Saturday 12:06 PM: Detection
- Circuit breaker detected stale market_exposure_daily (3 days old)
- Halted trading (correct safety behavior)
- Trading halted 105 minutes earlier (10:21 AM)
- System working as designed - preventing trading with degraded data

### 2026-07-04 Saturday 12:14 PM: Emergency Response
- Manually executed all 8 critical loaders
- Data refreshed and current as of Saturday noon
- Circuit breaker condition cleared
- BUT: Manual solution is not sustainable

### 2026-07-04 Saturday 5:23 PM: Permanent Fix
- Triggered new deployment workflow 28713688300
- Workflow completed successfully (STATUS=SUCCESS)
- Lambda build issue fixed
- Terraform apply executed successfully
- EventBridge rules deployed to AWS (~20 scheduler rules)
- ECS task definitions created
- IAM roles configured
- **Infrastructure now complete and ready for Monday**

## Root Cause: Cascade Failure

**Primary:** Lambda build failed (`ERROR: Failed to create lambda_algo.zip!`)
- This was a packaging/build issue, not a code issue
- Build script couldn't create the zip file for Terraform to deploy

**Cascade:** Because Lambda step failed, entire workflow stopped
- Workflow stopped at Lambda build (before Terraform apply)
- Terraform was never executed
- EventBridge rules were never created in AWS
- This wasn't detected because there was no alert for "deployment failed"

**Secondary:** No health check after deployment
- Terraform code was correct (rules set to `state = "ENABLED"`)
- But deployed infra was never verified
- No post-deployment check that rules actually exist in AWS

## Safety System Behavior: CORRECT ✓

The circuit breaker correctly protected the system:
1. ✅ Detected stale data (3 days old)
2. ✅ Halted trading immediately (correct response)
3. ✅ No silent fallbacks (explicit failure signal)
4. ✅ Transparent error (clear reason for halt)

This is exactly the behavior per GOVERNANCE.md fail-fast principle. **The system worked correctly—it just needed the underlying infrastructure to be fixed.**

## Fixes Implemented

### Immediate (Saturday 12:14 PM)
**Manual Loader Execution** — 8 critical loaders executed:
- stock_prices_daily, technical_data_daily, swing_trader_scores
- market_health_daily, market_exposure_daily
- quality_metrics, growth_metrics, momentum_metrics
- stock_scores

**Result:** Data refreshed, staleness cleared, trading ready

### Permanent (Saturday 5:23 PM)
**Infrastructure Deployment** — Workflow 28713688300 succeeded:
- ✅ EventBridge scheduler rules created (20+ rules for all loaders)
- ✅ ECS task definitions created (all loader tasks)
- ✅ IAM roles and permissions configured
- ✅ Dead-letter queues for error handling configured

**Result:** Automatic loader scheduling now functional for Monday onwards

## Monitoring & Verification

### Pre-Monday: Verification Scripts Created

**1. Infrastructure Check** — `scripts/verify_loader_infrastructure.sh`
```bash
./scripts/verify_loader_infrastructure.sh
# Verifies Terraform state contains all loader rules and tasks
# Run after deployment to confirm infrastructure exists
```

**2. Post-Deployment Health Check** — `scripts/check_post_deployment_health.sh`
```bash
./scripts/check_post_deployment_health.sh
# Runs AFTER Terraform apply completes
# Verifies EventBridge rules exist in AWS (not just in Terraform state)
# CRITICAL: Detects issues like this one before Monday
```

**3. Monday Monitoring** — `scripts/monitor_loaders_monday.sh`
```bash
# Run at 2:00 AM ET (morning pipeline)
./scripts/monitor_loaders_monday.sh morning

# Run at 4:00 PM ET (evening pipeline)
./scripts/monitor_loaders_monday.sh evening
# Monitors CloudWatch logs, checks database freshness
# Alerts on any missing or failed loaders
```

### Detailed Verification Plan
**See:** `steering/LOADER_INCIDENT_RESPONSE.md` → Monday Verification Checklist
- Morning pipeline (2:00-2:45 AM): stock_prices, technical, swing scores
- Evening pipeline (4:00-4:45 PM): market health, metrics, composite scores
- Orchestrator execution (5:30 PM): Verify trading proceeds with fresh data

## Prevention: Future Deployments

### 1. Detect Deployment Failures Early
**Add to CI/CD:** Post-deployment health check runs automatically
```bash
# After terraform apply completes:
./scripts/check_post_deployment_health.sh
# Fails the workflow if EventBridge rules not found in AWS
```

**Benefit:** Catches issues immediately instead of waiting for Monday's missing data

### 2. Monitor Loader Execution Automatically
**Future:** Add CloudWatch alarm
```
Alarm: If no loader execution in past 24 hours (Mon-Fri)
Action: Trigger SNS notification to on-call
```

**Benefit:** Alerts if loaders silently fail to run

### 3. Redundant Loader Trigger
**Future:** Dual trigger mechanism
- Primary: EventBridge scheduler (what failed)
- Fallback: Lambda cron function as backup trigger

**Benefit:** If EventBridge fails, fallback still runs loaders

### 4. Terraform Deployment Verification
**Add to Terraform:** Output validation
```hcl
output "eventbridge_rules_count" {
  value = length(aws_cloudwatch_event_rule.scheduled_loader)
  # If < 20, alert that rules weren't created
}
```

**Benefit:** Terraform apply fails if rules aren't created

## Operational Procedures Going Forward

### Monday 2026-07-07: CRITICAL MONITORING DAY

**2:00-2:45 AM ET:**
```bash
./scripts/monitor_loaders_monday.sh morning
# Checks: stock_prices_daily, technical_data_daily, swing_trader_scores
# Verifies database updated with fresh prices
```

**4:00-4:45 PM ET:**
```bash
./scripts/monitor_loaders_monday.sh evening
# Checks: market_health, market_exposure, metrics, stock_scores
# Verifies database has fresh market data for trading
```

**If HEALTHY:** System is stable, EventBridge scheduling works  
**If ISSUES:** Follow failure response procedures in verification plan

### Post-Monday: Ongoing Monitoring

**Weekly:** Confirm loaders ran Mon-Fri
```bash
# Monday AM: Verify previous week's data freshness
psql -c "SELECT MAX(date) FROM market_exposure_daily"
# Should be previous Friday
```

**Monthly:** Run infrastructure verification
```bash
./scripts/verify_loader_infrastructure.sh
# Confirms all EventBridge rules and task definitions still exist
```

## Documentation References

- **Incident Details:** `steering/DATA_LOADERS.md` (loader config)
- **Governance:** `steering/GOVERNANCE.md` (data quality fail-fast principle)
- **Operations:** `steering/OPERATIONS.md` (deployment procedures)
- **Verification Plan:** Memory `monday_loader_verification_plan.md`
- **Root Cause Analysis:** Memory `eventbridge_loader_deployment_issue.md`

## Key Learnings

1. **Code ≠ Deployed Infrastructure**
   - Correct Terraform code doesn't guarantee correct AWS resources
   - Need post-deployment verification that resources actually exist

2. **Cascade Failures**
   - One build step failure (Lambda) prevented entire infrastructure deployment
   - Need early detection of deployment step failures

3. **Monitoring Gap**
   - Silent failure (loaders didn't run, no alert)
   - Need monitoring that loaders ran, not just that code is deployed

4. **Circuit Breaker Works**
   - System correctly halted trading to prevent degraded data usage
   - This is the correct behavior—infrastructure just needs fixing

5. **Manual Recovery Critical**
   - On-demand loader execution was essential for Saturday recovery
   - Kept system functioning during deployment issues

## Success Criteria for Monday

✅ **ALL of these must be true:**

1. Morning loaders execute at scheduled times (2:15, 2:55, 3:15 AM)
2. CloudWatch logs show successful completion
3. Database shows fresh price data (from Monday morning)
4. Evening loaders execute at scheduled times (4:05, 4:20, 4:30 PM)
5. Database shows fresh market exposure and scores (for trading)
6. Orchestrator runs at 5:30 PM without data stale halt
7. Trading signals generate and positions evaluate with current data

**If all pass:** System is stable, EventBridge scheduling works reliably

**If any fail:** Follow failure response procedures in verification plan
