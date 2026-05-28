# Dry-Run Semantics - Clarified Behavior

**Issue:** #27 (COMPREHENSIVE_ISSUES.md)  
**Status:** 🟢 RESOLVED  
**Date:** 2026-05-28

---

## Overview

`dry_run` mode controls whether trades are actually executed. This document clarifies behavior across all components.

---

## Dry-Run Mode Behavior

### When `dry_run=true`

**✓ What Happens:**
- All 7 orchestrator phases run normally
- Position monitoring executes (Phase 3)
- Exit decisions are made (Phase 4) 
- Entry signals are ranked (Phase 5)
- **NO ORDERS ARE PLACED** (Phase 6 skipped)
- Reconciliation runs against live account (Phase 7)
- Full audit trail logged to `algo_audit_log`

**Purpose:** Validation-only mode. See what would trade without risking capital.

### When `dry_run=false`

**✓ What Happens:**
- All 7 phases run including LIVE ORDER EXECUTION (Phase 6)
- Positions opened/closed
- Stop losses adjusted
- Reconciliation against real account

**Purpose:** Production trading mode.

---

## Current Implementation

### Lambda Orchestrator
**File:** `lambda/algo_orchestrator/lambda_function.py`

**Behavior:**
```python
# Explicitly set for evening/preclose runs
if run_identifier in ('evening', 'preclose'):
    dry_run = event.get('dry_run', True)  # Default: safe mode
else:
    dry_run = event.get('dry_run', False)  # Default: normal execution
```

**Evening Run (5:30 PM ET):**
- Default: `dry_run=true` (safe - trading day over)
- Use case: Validate tomorrow's signals, no live trading

**Pre-Close Run (3:00 PM ET):**
- Default: `dry_run=true` (safety for intraday)
- Can override: Set `dry_run=false` if intended for live trading

**Morning/Afternoon Runs (9:30 AM / 1:00 PM ET):**
- Default: `dry_run=false` (enable live trading)
- Can override: Set `dry_run=true` for simulation

### Step Functions Pipeline
**File:** `terraform/modules/pipeline/main.tf:399-410`

**Behavior:**
```terraform
# EOD pipeline runs orchestrator in PAPER mode (prevents accidental trades)
Overrides = {
  ContainerOverrides = [{
    Environment = [
      { Name = "ORCHESTRATOR_EXECUTION_MODE", Value = "paper" },
      { Name = "ORCHESTRATOR_DRY_RUN", Value = "true" }
    ]
  }]
}
```

**Effect:** EOD pipeline can't modify live account even if code bugs.

### Environment Variables

**`ORCHESTRATOR_EXECUTION_MODE`** (Terraform-managed):
- `auto` - Use event signal preference
- `paper` - Never execute real trades
- `live` - Always execute trades (production only)

**`ORCHESTRATOR_DRY_RUN`** (Event-driven):
- `true` - Validation only
- `false` - Execute trades

---

## Usage Patterns

### Pattern 1: Morning Trading (Default)
```json
{
  "source": "eventbridge-scheduler",
  "run_identifier": "morning",
  "run_date": "now"
  /* dry_run defaults to false - LIVE TRADING */
}
```

### Pattern 2: Afternoon Rebalance (Default)
```json
{
  "source": "eventbridge-scheduler",
  "run_identifier": "afternoon",
  "run_date": "now"
  /* dry_run defaults to false - LIVE TRADING */
}
```

### Pattern 3: Evening Validation (Safe Default)
```json
{
  "source": "eventbridge-scheduler",
  "run_identifier": "evening",
  "run_date": "now"
  /* dry_run defaults to true - VALIDATION ONLY */
}
```

### Pattern 4: Force Simulation
```json
{
  "source": "test",
  "dry_run": true,
  "skip_freshness": true
  /* All phases run, no trades placed */
}
```

### Pattern 5: Live Test
```json
{
  "source": "api-manual",
  "execution_mode": "live",
  "dry_run": false
  /* Forces live trading (use with caution) */
}
```

---

## Safety Guarantees

### Fail-Closed Safeguards

1. **Evening Run Default:** `dry_run=true`
   - Even if EventBridge sends bad event, won't trade
   - Uses `event.get('dry_run', True)` with safe default

2. **Step Functions:** Always `dry_run=true` + `execution_mode=paper`
   - Double lock: both env vars must allow trading
   - EOD pipeline can't affect account

3. **Phase 6 Guard:** Even if `dry_run=false`, trade execution checks:
   ```python
   if self.dry_run or self.config['execution_mode'] == 'paper':
       logger.info("DRY RUN: skipping order execution")
       return  # No orders placed
   ```

### Audit Trail

All runs (dry or live) logged to `algo_audit_log`:
- Phases executed
- Signals generated
- Positions evaluated
- Trades simulated (dry) or executed (live)

---

## Testing Dry-Run

### Test Evening Run
```bash
aws lambda invoke \
  --function-name algo-algo-dev \
  --payload '{
    "source": "eventbridge-scheduler",
    "run_identifier": "evening",
    "run_date": "now"
  }' \
  /tmp/response.json

# Should log "Dry-run mode" or "skipping order execution"
aws logs tail /aws/lambda/algo-algo-dev --follow
```

### Test Live Morning Run
```bash
aws lambda invoke \
  --function-name algo-algo-dev \
  --payload '{
    "source": "eventbridge-scheduler",
    "run_identifier": "morning",
    "run_date": "now",
    "execution_mode": "live"
  }' \
  /tmp/response.json

# Should log actual order placement attempts
```

---

## Operational Checklist

Before going live:

- [ ] Evening orchestrator logs "DRY RUN" in Phase 6
- [ ] Morning orchestrator logs "Placing orders" in Phase 6
- [ ] Both runs complete Phase 7 reconciliation
- [ ] `algo_audit_log` has entries for all runs
- [ ] `ORCHESTRATOR_EXECUTION_MODE` matches tfvars setting
- [ ] No hardcoded `dry_run` in event payloads (use defaults)

---

## Future Improvements (Phase 2)

1. Add `run_identifier` to audit log (group by run type)
2. Dashboard widget showing dry_run vs live executions
3. Alerting if evening run accidentally trades
4. Simulation backtest output in dry-run summary

---

**Summary:** Dry-run is clear, safe, and properly enforced across all layers.
