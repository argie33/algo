# Backup Orchestrator Strategy

**Issue:** #32 (COMPREHENSIVE_ISSUES.md)  
**Status:** 🟡 DOCUMENTED  
**Date:** 2026-05-28

---

## Overview

This document describes the backup orchestrator strategy for handling primary orchestrator failures during trading hours (9:30 AM - 4:00 PM ET).

---

## Problem Statement

**Risk:** If morning Lambda crashes during market hours, next scheduled run is afternoon (1:00 PM ET), causing 3.5-hour trading gap.

**Current Schedule:**
- 9:30 AM ET: Morning run (PRIMARY)
- 1:00 PM ET: Afternoon run (SECONDARY)
- 3:00 PM ET: Pre-close run (FINAL)

---

## Proposed Solution

### 1. Health Check Lambda

**Functionality:**
- Runs every 30 minutes during trading hours
- Checks if morning/afternoon Lambda executed successfully
- Compares `algo_audit_log` timestamp vs. current time
- If last execution > 2 hours old → trigger alert + manual backup run

### 2. Backup Orchestrator Lambda

**Trigger:** Manual invocation via API or health check Lambda

**Behavior:**
- Same as regular orchestrator (all 7 phases)
- Logged to `algo_audit_log` with `run_type='backup'`
- Sends alert after execution (success or failure)

**Invocation:**
```bash
aws lambda invoke \
  --function-name algo-algo-dev \
  --payload '{
    "source": "manual-backup",
    "execution_mode": "live",
    "dry_run": false,
    "note": "Emergency backup run"
  }' \
  /tmp/response.json
```

### 3. Monitoring and Alerting

**CloudWatch Metrics:**
- `OrchestrationHealthCheck` (PASS/FAIL)
- `OrchestrationLastExecutionAge` (minutes)

---

## Implementation Plan

### Phase 1 (2-3 weeks): Health Check
1. Create `lambda/orchestrator-health-check/` Lambda
2. Deploy CloudWatch rule (every 90 min during trading)
3. Query `algo_audit_log` for latest execution
4. If > 2h stale → log ERROR + publish SNS alert

### Phase 2 (1-2 weeks): Auto-Recovery
1. Add backup orchestrator trigger to health check
2. Implement backup tracking in audit log
3. Set up monitoring dashboard

---

## Current Status

**What's Implemented:**
- Morning orchestrator at 9:30 AM ET ✓
- Afternoon orchestrator at 1:00 PM ET ✓
- Pre-close orchestrator at 3:00 PM ET ✓
- Manual invocation via Lambda CLI ✓

**What's Missing:**
- Automated health check Lambda ✗
- Automatic backup trigger on failure ✗

---

## Operational Procedure

### Emergency: Manually Trigger Backup

```bash
aws lambda invoke \
  --function-name algo-algo-dev \
  --payload '{
    "source": "manual",
    "execution_mode": "live",
    "dry_run": false
  }' \
  /tmp/response.json

# Monitor execution
aws logs tail /aws/lambda/algo-algo-dev --follow
```

---

**Summary:** Backup orchestrator strategy documented. Implementation deferred to Phase 2 (auto-recovery). Manual backup via Lambda CLI is available now.
