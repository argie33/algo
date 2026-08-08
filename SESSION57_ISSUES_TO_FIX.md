# SESSION 57 BUG FIXES - PRIORITIZED ISSUE LIST

## CRITICAL BLOCKERS (Fix First)

### Issue #1: Phase 8 Entry Execution Failing (9 Failed Trades)
- **Status**: BLOCKING - Prevents entry execution  
- **Evidence**: test_phase8_fix_v2.log shows "0 trades executed, 9 failed"
- **Error**: TypeError: unsupported operand type(s) for *: 'decimal.Decimal' and 'float'
- **Location**: executor_entry_handler.py line ~1178 (risk_pct calculation)
- **Claimed Fix**: Commit 5ace9007b (Session 56)
- **Verification**: Code HAS float() wrapping, but logs show error AFTER commit
- **Action**: 
  1. Verify code is actually correct (✓ Done - it is)
  2. Run test to reproduce on next trading day (Monday)
  3. If error persists, find other Decimal operations in entry flow

### Issue #2: Circuit Breaker Validation Error
- **Status**: BLOCKING - Halts orchestration
- **Evidence**: "dependency_failed: Circuit breaker check failed - data/validation error"
- **Impact**: Multiple orchestrator runs halted at Phase 2
- **Action**: Check circuit_breaker.py validation logic for data structure issues

### Issue #3: buy_sell_daily Loader FAILED Status
- **Status**: BLOCKING PHASE 7/8 - Stops signal generation
- **Evidence**: Phase 7 fails with "buy_sell_daily upstream loader not ready. Status: FAILED"
- **Progress**: 94.41% complete (not fully stuck, but insufficient for signal quality)
- **Action**: Check loader status and investigate why it's not completing

## MEDIUM PRIORITY (Related to Blocking Issues)

### Issue #4: Phase 8 Position Limit Halts
- **Status**: EXPECTED BEHAVIOR but needs monitoring
- **Evidence**: Many afternoon runs show "ok" status with position limit reached
- **Detail**: Correctly stops new entries when position count reaches max
- **Action**: Monitor that position accounting is accurate

### Issue #5: Exit Execution (Phase 6)
- **Status**: APPEARS OK (0 exits expected on 2026-08-07)
- **Evidence**: Phase 6 runs complete without errors
- **Action**: Needs testing with actual exit signals

## TESTING PLAN FOR MONDAY (2026-08-09)

1. Run orchestrator morning session
2. Monitor all 9 phases for completion
3. Check for any Decimal/float errors in logs
4. Verify trades execute successfully
5. Verify exits work if any positions need closing
6. Document any new issues

## MEMORY FIXES NEEDED

- Session 56 memory claims "ALL 9 PHASES OK" - needs update to reflect actual status
- Remove claims about "production ready" until verified on real trading day
- Document all actual blocking issues
- Remove inaccurate memory entries
