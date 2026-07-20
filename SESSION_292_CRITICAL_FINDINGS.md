# Session 292: CRITICAL BYPASS & INCONSISTENCY FOUND

## Issue Summary

**CRITICAL:** Code-level inconsistency between halt_flag_manager and orchestrator regarding whether halt flag management is critical or gracefully degradable.

## Root Cause: Design Contradiction

### What Session 290 Did
- Modified `clear_halt_flag()` to return `False` on error (graceful degradation)
- Added RDS fallback to prevent crashes
- Comment: "Don't re-raise - allow orchestrator to continue despite halt flag management failure"

### What Orchestrator Does
- Orchestrator checks: `if not halt_clear_result: raise RuntimeError(...)`
- Comment (line 992-994): "Halt flag MUST succeed or orchestrator fails. If we can't manage halt flags, we have no safety guarantees - must fail-fast."

### The Contradiction
- Session 290 made clear_halt_flag() return False (non-fatal)
- Orchestrator treats False as fatal and raises RuntimeError
- Result: Orchestrator STILL CRASHES even with the Session 290 "fix"

**This explains the error run: `RUN-2026-07-19-230458: error` with message "Halt flag management failed..."**

## Code Evidence

### halt_flag_manager.py line 690 (Session 290 fix)
```python
# Don't re-raise - allow orchestrator to continue despite halt flag management failure
# This is a circuit breaker: prefer trading with stale halt status over not trading at all
return False
```

### orchestrator.py line 1009-1014 (CONTRADICTS the fix)
```python
if not halt_clear_result:
    raise RuntimeError(
        "[GOVERNANCE VIOLATION] Halt flag could not be cleared despite fresh data. "
        "This is a critical safety failure - we may be stuck in halted mode or the flag is stale. "
        "Orchestrator MUST fail. Check database connectivity (RDS and DynamoDB) and AWS credentials."
    )
```

## The Real Issue

**The Session 290 fix was INCOMPLETE because:**
1. clear_halt_flag() was made graceful (returns False)
2. BUT orchestrator still requires success (raises RuntimeError on False)
3. Net result: Orchestrator still crashes

**The fix created a false sense of safety** - the code catches exceptions gracefully, but then orchestrator ignores the graceful fallback and crashes anyway.

## Design Decision Required

Two options:

### Option A: Halt flag IS critical (Fail-Fast)
- Remove graceful return False from clear_halt_flag()
- Make clear_halt_flag() RAISE RuntimeError if BOTH DynamoDB and RDS fail
- Orchestrator expectation (line 992-994) becomes correct
- Pros: Explicit failure when safety mechanism unavailable
- Cons: Orchestrator crashes on credential issues

### Option B: Halt flag is nice-to-have (Graceful Degradation)
- Keep clear_halt_flag() returning False gracefully
- Change orchestrator to accept False (don't raise RuntimeError)
- Orchestrator continues even if halt flag can't be cleared
- Pros: Trading continues despite transient credential issues
- Cons: Stale halt flag could persist

## Recommendation

**Choose Option A (Fail-Fast)** because:
1. Halt flag is a safety mechanism (line 992-994 is correct)
2. If we can't enforce safety, we must fail - no trading during credential failures
3. This aligns with GOVERNANCE principle: "Fail-fast on critical safety checks"
4. AWS credential issues are RARE and should be fixed, not hidden
5. Graceful degradation here masks real infrastructure problems

## Fix Strategy

1. Modify `clear_halt_flag()` to RAISE RuntimeError when BOTH DynamoDB and RDS unavailable
2. Modify `set_halt_flag()` similarly (also has graceful False return)
3. Remove the `if not halt_clear_result:` check in orchestrator (will crash before returning False)
4. Add logging to show which storage system succeeded

## Additional Issues Found

- `stock_symbols` table sometimes empty (halted 2 orchestrator runs)
- Alpaca credentials missing in some environments (halted multiple runs)
- These are OPERATIONAL issues, not code bypasses, but worth noting

## Commits to Create

1. Fix halt_flag_manager to fail-fast (raise RuntimeError)
2. Clean up orchestrator exception handling (no need for False check if it raises)
3. Add audit logging to show which storage backend succeeded
