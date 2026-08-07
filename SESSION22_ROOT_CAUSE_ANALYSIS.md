# Session 22 - Root Cause Analysis: Circuit Breaker Halt

## THE REAL ISSUE

**Positions were entered PRE-MARKET (05:03 ET) during DRY_RUN mode, bypassing market hours guards.**

### Timeline

1. **05:03 ET** - Orchestrator runs with dry_run=True (or ORCHESTRATOR_DRY_RUN env set)
   - Pre-flight market hours guard bypassed because dry_run=True
   - Phase 8 market hours guard also bypassed when dry_run is active
   - 18 positions created

2. **05:03-05:12 ET** - Positions recorded in database with pre-market timestamps
   - Database shows UTC 09:03-09:12 = ET 05:03-05:12
   - All created during pre-market hours

3. **09:30 ET** - Market opens
   - Pre-market orders execute at market open prices (can have gaps)
   - 5 positions get bad fills from overnight gaps or opening volatility

4. **~12:06 ET** - 5 positions hit their stops (3 hours later)
   - All 5 are consecutive losses: -364, -373, -377, -284, -369
   - Circuit breaker threshold is 5 losses (paper mode)
   - Orchestrator halts: "Halted: Consecutive Losses Limit: 5 consecutive losses >= 5"

### Why This Is A Bug

**Dry_run mode should NOT create real positions in the database.**

The intent of dry_run is:
- Simulate what the orchestrator would do
- Log the actions that WOULD execute
- Do NOT actually execute anything

But Phase 6 and Phase 8 are creating real positions even when dry_run=True.

### The Code Bug

In `algo/orchestration/orchestrator.py` line 1993:
```python
if not self.dry_run and not allow_outside_hours and not (MARKET_OPEN_TIME <= now_et < MARKET_CLOSE_TIME):
    # Skip pre-market runs
```

This says: "If NOT dry_run AND outside hours, then skip"

Translation: "If dry_run=True, ignore market hours completely and run anyway"

This was probably intentional (allow testing at any time with dry_run), but it allowed real positions to be created pre-market.

### Secondary Bugs

1. **Phase 6 doesn't respect dry_run for exit execution**
   - Should report "DRY-RUN: would exit X positions" not actually exit
   
2. **Phase 8 doesn't respect dry_run for entry execution**  
   - Should report "DRY-RUN: would enter Y positions" not actually enter

3. **No safeguard preventing dry_run + real position creation**
   - Should either:
     a) Truly skip all trading operations when dry_run=True
     b) OR block dry_run mode before market hours
     c) OR add a separate "staging" flag to distinguish testing from simulation

### Signal Quality Issue (Secondary)

The 5 positions that lost money had signal quality scores of 63-68 (close to minimum of 60). This is a separate issue:

- Signals were barely above minimum quality threshold
- High risk scores (79-85)
- Suggests Phase 7 signal generation needs improvement
- Recommend raising min_signal_quality_score or improving signal algorithm

But even if signals were perfect, pre-market entry execution is a bug that needs fixing.

### Recommended Fixes (Priority Order)

**CRITICAL:**
1. Remove dry_run bypass from market hours guard
2. Ensure Phase 6 and Phase 8 don't create positions when dry_run=True
3. Add explicit safeguard: `if dry_run: return {"phases": [...], "skipped": True, "reason": "dry_run_mode"}`

**HIGH:**
1. Add logging to confirm when dry_run is active (currently silent)
2. Raise min_signal_quality_score to 70 (was 60, losing trades were 63-68)
3. Clear ORCHESTRATOR_DRY_RUN from environment if testing is done

**MEDIUM:**
1. Document what dry_run is actually supposed to do
2. Consider renaming dry_run to "test_mode" or "simulation_mode" for clarity
3. Add metrics for "expected trades" vs "actual trades" in dry_run reports

### How to Verify Fix

```bash
# This should NOW skip pre-market and log why
python scripts/run_local_orchestrator.py --afternoon --force

# Should see: "[MARKET_HOURS_GUARD] Orchestrator run attempted outside market hours"
# NOT: "Starting AFTERNOON orchestrator run..."
```

### Current Status

- **Bug Severity**: CRITICAL - allows real positions during simulated runs
- **Data Loss**: 5 real losses from pre-market entry execution
- **Code Risk**: High - dry_run is supposed to be safe but it's not
- **Fix Complexity**: Medium - requires coordinating Phases 6-9
